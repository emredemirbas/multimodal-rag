"""Documentation approval is authenticated, explicit and separate from capture."""

import json
from uuid import uuid4

import pytest

from app.models import ProjectCreate
from conftest import auth_headers
from test_curriculum_api_integration import (
    assert_private, context_api, context_body, create_context,
)
from test_postgres_integration import isolated_postgres_url
from test_documentation_integration import CATALOG_ID, PRIVATE_TEXT, SyntheticFetcher, get_document


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def document_api(context_api):
    client, state = context_api
    app = client._transport.app
    fetcher = SyntheticFetcher()
    app.state.documentation_fetcher = fetcher
    state["fetcher"], state["app"] = fetcher, app
    state["documentation_root"] = f"/api/v1/projects/{state['project'].id}/curriculum/documentation"
    body = context_body(state)
    body["learner"]["allow_external_documentation"] = True
    context = await create_context(client, state, body)
    state["context"] = context
    state["documentation_list"] = state["path"] + "/" + context["id"] + "/documentation"
    yield client, state


def approval_json(key="http-document-approval", **changes):
    return {"idempotency_key": key, "catalog_id": CATALOG_ID,
            "catalog_sha256": get_document(CATALOG_ID).fingerprint,
            "consent": "retrieve_and_retain"} | changes


async def approve(client, state, body=None):
    response = await client.post(state["documentation_list"], headers=auth_headers(),
                                 json=approval_json() if body is None else body)
    assert response.status_code == 201, response.text
    assert_private(response)
    return response.json()


def document_path(state, document_id):
    return state["documentation_root"] + "/" + document_id


async def test_document_http_approval_never_fetches_and_capture_returns_safe_plaintext(document_api):
    client, state = document_api
    catalog = await client.get(state["documentation_root"] + "/catalog", headers=auth_headers())
    assert catalog.status_code == 200
    assert_private(catalog)
    assert CATALOG_ID in catalog.text and get_document(CATALOG_ID).fingerprint in catalog.text
    saved = await approve(client, state)
    assert saved["status"] == "pending" and saved["snapshot"] is None
    assert saved["context_id"] == state["context"]["id"]
    path = document_path(state, saved["id"])
    assert (await client.get(path, headers=auth_headers())).json() == saved
    listed = await client.get(state["documentation_list"], headers=auth_headers())
    assert listed.status_code == 200 and listed.json() == [saved]
    assert_private(listed)
    assert state["fetcher"].calls == []
    command = {"idempotency_key": "http-capture-command"}
    capture = await client.post(path + "/capture", headers=auth_headers(), json=command)
    assert capture.status_code == 200, capture.text
    assert_private(capture)
    captured = capture.json()
    assert captured["status"] == "captured" and captured["failure_code"] is None
    assert captured["snapshot"]["url"] == get_document(CATALOG_ID).url
    assert captured["snapshot"]["detected_version"] is None
    assert "".join(excerpt["text"] for excerpt in captured["snapshot"]["excerpts"]) == PRIVATE_TEXT
    assert (await client.post(path + "/capture", headers=auth_headers(), json=command)).json() == captured
    assert (await client.get(path, headers=auth_headers())).json() == captured
    assert state["fetcher"].calls == [CATALOG_ID]
    deleted = await client.delete(path, headers=auth_headers())
    assert deleted.status_code == 204 and not deleted.content
    assert_private(deleted)
    missing = await client.get(path, headers=auth_headers())
    assert missing.status_code == 404
    assert_private(missing)


async def test_document_http_all_routes_require_auth_and_exact_scope_before_io(document_api):
    client, state = document_api
    saved = await approve(client, state)
    path = document_path(state, saved["id"])
    requests = [
        ("GET", state["documentation_root"] + "/catalog", None),
        ("POST", state["documentation_list"], approval_json()),
        ("GET", state["documentation_list"], None), ("GET", path, None),
        ("DELETE", path, None), ("POST", path + "/capture", {"idempotency_key": "scope-capture-command"}),
    ]
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Unrelated documentation project"))
    for method, endpoint, payload in requests:
        unauthenticated = await client.request(method, endpoint, json=payload)
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["www-authenticate"] == "Bearer"
        assert_private(unauthenticated)
        foreign = await client.request(method, endpoint, headers=auth_headers("tenant-b"), json=payload)
        assert foreign.status_code == 404
        assert_private(foreign)
        # Catalog is a project-scoped capability listing: another accessible
        # project may read it, but may not use this project's context/document.
        if endpoint.endswith("/catalog"):
            continue
        wrong_project = endpoint.replace(str(state["project"].id), str(other.id))
        response = await client.request(method, wrong_project, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)
    assert state["fetcher"].calls == []


async def test_document_http_membership_is_rechecked_after_identity_mapping(document_api, monkeypatch):
    client, state = document_api
    saved = await approve(client, state)
    original = state["store"].bootstrap_principal

    def revoke_after_mapping(principal):
        actor = original(principal)
        with state["store"]._connect() as connection:
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
        return actor

    monkeypatch.setattr(state["store"], "bootstrap_principal", revoke_after_mapping)
    path = document_path(state, saved["id"])
    for method, endpoint, payload in [
        ("GET", state["documentation_root"] + "/catalog", None),
        ("POST", state["documentation_list"], approval_json()),
        ("GET", state["documentation_list"], None), ("GET", path, None), ("DELETE", path, None),
        ("POST", path + "/capture", {"idempotency_key": "revoked-http-capture"}),
    ]:
        response = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)
    assert state["fetcher"].calls == []


@pytest.mark.parametrize("changed", [
    {"url": "http://127.0.0.1/internal"}, {"tenant_id": "forged"},
    {"context_id": str(uuid4())}, {"approved_by": str(uuid4())},
    {"consent": True}, {"consent": "yes"}, {"catalog_sha256": "bad"},
    {"idempotency_key": 12345678}, {"snapshot": {}},
])
async def test_document_http_rejects_untrusted_metadata_and_coercions_without_fetch(document_api, changed):
    client, state = document_api
    response = await client.post(state["documentation_list"], headers=auth_headers(),
                                 json=approval_json(**changed))
    assert response.status_code == 422, response.text
    assert_private(response)
    assert (await client.get(state["documentation_list"], headers=auth_headers())).json() == []
    assert state["fetcher"].calls == []


async def test_document_http_duplicate_json_oversized_chunked_body_and_capture_fields(document_api):
    client, state = document_api
    body = json.dumps(approval_json())[:-1] + ',"consent":"retrieve_and_retain"}'
    duplicate = await client.post(state["documentation_list"], headers=auth_headers(), content=body)
    assert duplicate.status_code == 422
    assert_private(duplicate)

    async def chunks():
        yield b'{"unexpected":"'
        yield b"x" * 16_384
        yield b'"}'

    oversized = await client.post(state["documentation_list"], headers=auth_headers(), content=chunks())
    assert oversized.status_code == 413
    assert_private(oversized)
    saved = await approve(client, state)
    for payload in [{}, {"idempotency_key": 12345678}, {"idempotency_key": "capture-key", "url": "https://example.com/"}]:
        invalid = await client.post(document_path(state, saved["id"]) + "/capture",
                                    headers=auth_headers(), json=payload)
        assert invalid.status_code == 422
        assert_private(invalid)
    assert state["fetcher"].calls == []


async def test_document_http_requires_saved_external_document_permission(document_api):
    client, state = document_api
    body = context_body(state, "http-docs-forbidden-context")
    context = await create_context(client, state, body)
    path = state["path"] + "/" + context["id"] + "/documentation"
    response = await client.post(path, headers=auth_headers(), json=approval_json())
    assert response.status_code in {409, 422}
    assert_private(response)
    assert state["fetcher"].calls == []


@pytest.mark.parametrize("target", ["context", "source", "project"])
async def test_document_http_parent_deletion_removes_snapshot_and_capture_replay(document_api, target):
    client, state = document_api
    saved = await approve(client, state)
    path = document_path(state, saved["id"])
    command = {"idempotency_key": "delete-http-capture"}
    captured = await client.post(path + "/capture", headers=auth_headers(), json=command)
    assert captured.status_code == 200
    if target == "context":
        deleted = await client.delete(state["path"] + "/" + state["context"]["id"], headers=auth_headers())
        assert deleted.status_code == 204
    elif target == "source":
        with state["store"]._connect() as connection:
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (state["principal"].tenant_id, state["project"].id, state["source"].id))
    else:
        state["service"].delete_project(state["principal"], state["project"].id)
    for method, endpoint, payload in [("GET", path, None), ("DELETE", path, None),
                                      ("POST", path + "/capture", command)]:
        response = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)
    assert state["fetcher"].calls == [CATALOG_ID]


async def test_document_http_has_no_fake_inmemory_capture_capability(client):
    project = await client.post("/api/v1/projects", headers=auth_headers(), json={"title": "Synthetic memory workspace"})
    assert project.status_code == 201
    root = f"/api/v1/projects/{project.json()['id']}/curriculum/documentation"
    response = await client.get(root + "/catalog", headers=auth_headers())
    assert response.status_code == 503
    assert_private(response)
