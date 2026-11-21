"""Explicit reviewed activation is private, scoped, strict and independently readable."""

from uuid import uuid4

import pytest

from app.models import ProjectCreate
from conftest import auth_headers
from test_curriculum_api_integration import assert_private, context_api, create_context
from test_curriculum_draft_api_integration import create_draft, draft_body, draft_path, replacement
from test_curriculum_draft_documents_api_integration import bound_document_api, documented_body, save_draft
from test_postgres_integration import isolated_postgres_url


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def activation_body(key="reviewed-http-activation", revision=1):
    return {"idempotency_key": key, "expected_revision": revision,
            "consent": "activate_reviewed_revision"}


def assignment_path(state, assignment_id):
    return f"/api/v1/projects/{state['project'].id}/curriculum/assignments/{assignment_id}"


async def activate(client, state, draft, body=None):
    response = await client.post(draft_path(state, draft["id"]) + "/activate", headers=auth_headers(),
                                 json=body or activation_body())
    assert response.status_code == 201, response.text
    assert_private(response)
    return response.json()


async def test_activation_http_is_explicit_and_returns_exact_immutable_revision(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    draft = await create_draft(client, state, context, body)
    path = draft_path(state, draft["id"])
    empty = await client.get(path + "/activation", headers=auth_headers())
    assert empty.status_code == 200 and empty.json() == {"activation": None}
    assert_private(empty)
    activated = await activate(client, state, draft)
    assert set(activated) == {"id", "tenant_id", "project_id", "draft_id", "context_id", "revision",
                              "activated_at", "activated_by", "draft"}
    assert activated["id"] != draft["id"]
    assert activated["tenant_id"] == "tenant-a" and activated["project_id"] == str(state["project"].id)
    assert activated["draft_id"] == draft["id"] and activated["context_id"] == context["id"]
    assert activated["revision"] == 1 and activated["draft"] == draft
    assert await activate(client, state, draft) == activated
    for endpoint, expected in [(path + "/activation", {"activation": activated}),
                               (assignment_path(state, activated["id"]), activated)]:
        response = await client.get(endpoint, headers=auth_headers())
        assert response.status_code == 200 and response.json() == expected
        assert_private(response)
    edited = await client.put(path, headers=auth_headers(), json=replacement(body))
    assert edited.status_code == 200 and edited.json()["revision"] == 2
    old = await client.get(assignment_path(state, activated["id"]), headers=auth_headers())
    assert old.json() == activated
    assert (await client.get(path + "/activation", headers=auth_headers())).json() == {"activation": activated}
    stale = await client.post(path + "/activate", headers=auth_headers(), json=activation_body("stale-http-activation"))
    assert stale.status_code == 409 and stale.json()["code"] == "draft_revision_conflict"
    assert_private(stale)
    second = await activate(client, state, draft, activation_body("stale-http-activation", 2))
    assert second["draft"] == edited.json() and second["id"] != activated["id"]
    assert (await client.get(path + "/activation", headers=auth_headers())).json() == {"activation": second}


async def test_activation_http_idempotency_new_keys_archive_and_shared_command_namespace(context_api):
    client, state = context_api
    context = await create_context(client, state)
    draft = await create_draft(client, state, context)
    path = draft_path(state, draft["id"])
    created_key = draft_body(context)["idempotency_key"]
    collision = await client.post(path + "/activate", headers=auth_headers(), json=activation_body(created_key))
    assert collision.status_code == 409 and collision.json()["code"] == "idempotency_conflict"
    assert_private(collision)
    first = await activate(client, state, draft)
    assert await activate(client, state, draft, activation_body("new-key-same-review")) == first
    collision = await client.put(path, headers=auth_headers(),
                                 json=replacement(draft_body(context), key="reviewed-http-activation"))
    assert collision.status_code == 409 and collision.json()["code"] == "idempotency_conflict"
    state["service"].archive_project(state["principal"], state["project"].id)
    assert await activate(client, state, draft) == first
    blocked = await client.post(path + "/activate", headers=auth_headers(), json=activation_body("archived-new-http-key"))
    assert blocked.status_code == 409 and blocked.json()["code"] == "project_archived"
    assert_private(blocked)
    read = await client.get(assignment_path(state, first["id"]), headers=auth_headers())
    assert read.status_code == 200 and read.json() == first
    assert_private(read)


@pytest.mark.parametrize("field,value", [
    ("consent", None), ("consent", True), ("consent", "retrieve_and_retain"),
    ("expected_revision", None), ("expected_revision", True), ("expected_revision", "1"),
    ("expected_revision", 0), ("expected_revision", -1), ("expected_revision", 2_147_483_648),
    ("idempotency_key", "short"), ("idempotency_key", "a" * 129), ("idempotency_key", "private key"),
    ("tenant_id", "private-client-tenant"), ("project_id", str(uuid4())),
    ("draft", {"title": "private-client-evidence"}), ("activated_by", str(uuid4())),
])
async def test_activation_http_rejects_missing_consent_coercion_bounds_and_injected_metadata(context_api, field, value):
    client, state = context_api
    context = await create_context(client, state)
    draft = await create_draft(client, state, context)
    body = activation_body()
    if value is None:
        del body[field]
    else:
        body[field] = value
    response = await client.post(draft_path(state, draft["id"]) + "/activate", headers=auth_headers(), json=body)
    assert response.status_code == 422
    assert response.json() == {"code": "validation_error", "detail": "Request validation failed."}
    assert "private-client" not in response.text
    assert_private(response)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_assignment_versions").fetchone()["n"] == 0
        assert connection.execute("SELECT count(*) AS n FROM curriculum_draft_commands").fetchone()["n"] == 1


async def test_activation_http_all_endpoints_require_authentication_and_exact_scopes(context_api):
    client, state = context_api
    context = await create_context(client, state)
    draft = await create_draft(client, state, context)
    activated = await activate(client, state, draft)
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Other assignment project"))
    for method, endpoint, payload in [
        ("POST", draft_path(state, draft["id"]) + "/activate", activation_body()),
        ("GET", draft_path(state, draft["id"]) + "/activation", None),
        ("GET", assignment_path(state, activated["id"]), None),
    ]:
        missing = await client.request(method, endpoint, json=payload)
        assert missing.status_code == 401 and missing.headers["www-authenticate"] == "Bearer"
        assert_private(missing)
        foreign = await client.request(method, endpoint, headers=auth_headers("tenant-b"), json=payload)
        assert foreign.status_code == 404
        assert_private(foreign)
        unrelated = await client.request(method, endpoint.replace(str(state["project"].id), str(other.id)),
                                          headers=auth_headers(), json=payload)
        assert unrelated.status_code == 404
        assert_private(unrelated)
    for method, endpoint, payload in [
        ("POST", draft_path(state, str(uuid4())) + "/activate", activation_body("missing-http-draft")),
        ("GET", draft_path(state, str(uuid4())) + "/activation", None),
        ("GET", assignment_path(state, str(uuid4())), None),
    ]:
        missing = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert missing.status_code == 404
        assert_private(missing)


async def test_activation_http_rechecks_membership_after_identity_resolution(context_api, monkeypatch):
    client, state = context_api
    context = await create_context(client, state)
    draft = await create_draft(client, state, context)
    activated = await activate(client, state, draft)
    original = state["store"].bootstrap_principal

    def revoke(principal):
        actor = original(principal)
        with state["store"]._connect() as connection:
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
        return actor

    monkeypatch.setattr(state["store"], "bootstrap_principal", revoke)
    for method, endpoint, payload in [
        ("POST", draft_path(state, draft["id"]) + "/activate", activation_body()),
        ("GET", draft_path(state, draft["id"]) + "/activation", None),
        ("GET", assignment_path(state, activated["id"]), None),
    ]:
        denied = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert denied.status_code == 404
        assert_private(denied)


async def test_activation_http_captured_evidence_stays_pinned_and_document_removal_erases_it(bound_document_api):
    client, state = bound_document_api
    draft = await save_draft(client, state, documented_body(state))
    activated = await activate(client, state, draft)
    assert activated["draft"] == draft
    assert activated["draft"]["assignment"]["documentation_snapshots"] == [state["document"]["snapshot"]]
    assert state["fetcher"].calls == [state["document"]["policy"]["id"]]
    deleted = await client.delete(state["document_root"] + "/" + state["document"]["id"], headers=auth_headers())
    assert deleted.status_code == 204
    for endpoint in [assignment_path(state, activated["id"]), draft_path(state, draft["id"]) + "/activation"]:
        missing = await client.get(endpoint, headers=auth_headers())
        assert missing.status_code == 404
        assert_private(missing)
    replay = await client.post(draft_path(state, draft["id"]) + "/activate", headers=auth_headers(), json=activation_body())
    assert replay.status_code == 404
    assert_private(replay)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_assignment_versions").fetchone()["n"] == 0
        assert connection.execute("SELECT count(*) AS n FROM curriculum_draft_commands").fetchone()["n"] == 0


async def test_activation_http_memory_backend_fails_closed_without_fabricated_versions(client):
    project = await client.post("/api/v1/projects", headers=auth_headers(), json={"title": "Synthetic memory assignment"})
    assert project.status_code == 201
    root = f"/api/v1/projects/{project.json()['id']}/curriculum"
    for method, endpoint, body in [
        ("POST", root + f"/drafts/{uuid4()}/activate", activation_body()),
        ("GET", root + f"/drafts/{uuid4()}/activation", None),
        ("GET", root + f"/assignments/{uuid4()}", None),
    ]:
        unavailable = await client.request(method, endpoint, headers=auth_headers(), json=body)
        assert unavailable.status_code == 503 and unavailable.json()["code"] == "curriculum_not_configured"
        assert_private(unavailable)
