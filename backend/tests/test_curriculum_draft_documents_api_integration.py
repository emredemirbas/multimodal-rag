"""HTTP selection of captured documents never grants implicit fetch permission."""

import json
from uuid import uuid4

import pytest

from app.models import ProjectCreate
from conftest import auth_headers
from test_curriculum_api_integration import assert_private, context_api, context_body, create_context
from test_curriculum_draft_api_integration import create_path, draft_body, draft_path, replacement
from test_documentation_api_integration import approval_json
from test_documentation_integration import SyntheticFetcher
from test_postgres_integration import isolated_postgres_url


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def bound_document_api(context_api):
    client, state = context_api
    body = context_body(state)
    body["learner"].update(allow_extensions=True, allow_external_documentation=True)
    context = await create_context(client, state, body)
    state["context"] = context
    state["fetcher"] = SyntheticFetcher(text="Authored example: expose a typed item endpoint.")
    client._transport.app.state.documentation_fetcher = state["fetcher"]
    document_list = state["path"] + "/" + context["id"] + "/documentation"
    approval = await client.post(document_list, headers=auth_headers(), json=approval_json())
    assert approval.status_code == 201, approval.text
    state["document_root"] = f"/api/v1/projects/{state['project'].id}/curriculum/documentation"
    path = state["document_root"] + "/" + approval.json()["id"]
    capture = await client.post(path + "/capture", headers=auth_headers(),
                                json={"idempotency_key": "draft-http-document-capture"})
    assert capture.status_code == 200, capture.text
    state["document"] = capture.json()
    state["document_list"] = document_list
    yield client, state


def documented_body(state, key="document-backed-draft-http"):
    body = draft_body(state["context"], key)
    body["documentation_ids"] = [state["document"]["id"]]
    body["content"]["requirements"].append({
        "id": "typed-item", "label": "extension", "description": "Expose a typed item endpoint.",
        "objective_ids": ["health"], "tutorial_segment_ids": [],
        "documentation_excerpt_ids": [state["document"]["snapshot"]["excerpts"][0]["id"]],
    })
    body["content"]["acceptance_criteria"].append({
        "id": "typed-response", "description": "The item response has the documented shape.",
        "requirement_ids": ["typed-item"],
    })
    body["content"]["rubric"][0]["acceptance_criterion_ids"].append("typed-response")
    return body


async def save_draft(client, state, body):
    response = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert response.status_code == 201, response.text
    assert_private(response)
    return response.json()


async def test_document_draft_http_create_replace_read_history_keep_stable_provenance(bound_document_api):
    client, state = bound_document_api
    body = documented_body(state)
    first = await save_draft(client, state, body)
    assert first["documentation_ids"] == body["documentation_ids"]
    assert first["assignment"]["documentation_snapshots"] == [state["document"]["snapshot"]]
    assert first["assignment"]["draft"]["requirements"][-1]["label"] == "extension"
    assert first["assignment"]["draft"]["requirements"][0]["label"] == "covered"
    path = draft_path(state, first["id"])
    edit = replacement(body)
    second = await client.put(path, headers=auth_headers(), json=edit)
    assert second.status_code == 200 and second.json()["revision"] == 2
    assert_private(second)
    assert second.json()["assignment"]["documentation_snapshots"] == [state["document"]["snapshot"]]
    for endpoint, expected in [(path, second.json()), (path + "/revisions/1", first)]:
        read = await client.get(endpoint, headers=auth_headers())
        assert read.status_code == 200 and read.json() == expected
        assert_private(read)
    assert await save_draft(client, state, body) == first
    assert state["fetcher"].calls == [state["document"]["policy"]["id"]]


@pytest.mark.parametrize("selection", [None, []])
async def test_document_draft_http_never_auto_selects_or_fetches_cited_document(bound_document_api, selection):
    client, state = bound_document_api
    body = documented_body(state)
    if selection is None:
        del body["documentation_ids"]
    else:
        body["documentation_ids"] = selection
    response = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert response.status_code == 422 and response.json()["code"] == "invalid_curriculum_draft"
    assert_private(response)
    assert state["fetcher"].calls == [state["document"]["policy"]["id"]]
    assert (await save_draft(client, state, documented_body(state)))["revision"] == 1


@pytest.mark.parametrize("invalid", ["duplicate", "too_many", "malformed", "null", "object", "numeric"])
async def test_document_selection_http_is_bounded_unique_and_typed(bound_document_api, invalid):
    client, state = bound_document_api
    body = documented_body(state)
    document_id = state["document"]["id"]
    body["documentation_ids"] = {
        "duplicate": [document_id, document_id], "too_many": [str(uuid4()) for _ in range(21)],
        "malformed": ["not-a-document-id"], "null": None,
        "object": [{"id": document_id}], "numeric": [1],
    }[invalid]
    response = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert_private(response)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_draft_commands").fetchone()["n"] == 0


@pytest.mark.parametrize("field", ["documentation_snapshots", "policy", "retrieved_at", "content_sha256"])
async def test_document_draft_http_accepts_only_ids_and_rejects_client_provenance(bound_document_api, field):
    client, state = bound_document_api
    body = documented_body(state)
    body[field] = {"private": "client-supplied-document-payload"}
    response = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert "client-supplied-document-payload" not in response.text
    assert_private(response)


async def test_document_draft_http_wrong_context_and_uncaptured_document_fail_without_receipts(bound_document_api):
    client, state = bound_document_api
    body = documented_body(state)
    other_body = context_body(state, "other-doc-draft-context")
    other_body["learner"].update(allow_extensions=True, allow_external_documentation=True)
    other_context = await create_context(client, state, other_body)
    wrong = await client.post(create_path(state, other_context), headers=auth_headers(), json=body)
    assert wrong.status_code == 404
    assert_private(wrong)
    pending = await client.post(state["document_list"], headers=auth_headers(),
                               json=approval_json("pending-doc-draft-http"))
    assert pending.status_code == 201
    body["documentation_ids"] = [pending.json()["id"]]
    uncaptured = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert uncaptured.status_code == 422 and uncaptured.json()["code"] == "invalid_curriculum_draft"
    assert_private(uncaptured)
    assert state["fetcher"].calls == [state["document"]["policy"]["id"]]
    await save_draft(client, state, documented_body(state))
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_draft_commands").fetchone()["n"] == 1


async def test_document_draft_http_scoped_authentication_precedes_binding(bound_document_api):
    client, state = bound_document_api
    body = documented_body(state)
    first = await save_draft(client, state, body)
    path = draft_path(state, first["id"])
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Unrelated documented draft"))
    for method, endpoint, payload in [
        ("POST", create_path(state, state["context"]), body),
        ("PUT", path, replacement(body)), ("GET", path, None),
        ("GET", path + "/revisions/1", None), ("DELETE", path, None),
    ]:
        unauthenticated = await client.request(method, endpoint, json=payload)
        assert unauthenticated.status_code == 401
        assert_private(unauthenticated)
        foreign = await client.request(method, endpoint, headers=auth_headers("tenant-b"), json=payload)
        assert foreign.status_code == 404
        assert_private(foreign)
        wrong_project = await client.request(method, endpoint.replace(str(state["project"].id), str(other.id)),
                                              headers=auth_headers(), json=payload)
        assert wrong_project.status_code == 404
        assert_private(wrong_project)
    assert (await client.get(path, headers=auth_headers())).json() == first
    assert state["fetcher"].calls == [state["document"]["policy"]["id"]]


async def test_document_draft_http_delete_cascades_historical_draft_and_replay_receipts(bound_document_api):
    client, state = bound_document_api
    body = documented_body(state)
    first = await save_draft(client, state, body)
    path = draft_path(state, first["id"])
    edit = replacement(draft_body(state["context"]), key="remove-doc-selection-http")
    edit["documentation_ids"] = []
    second = await client.put(path, headers=auth_headers(), json=edit)
    assert second.status_code == 200 and second.json()["documentation_ids"] == []
    deleted = await client.delete(state["document_root"] + "/" + state["document"]["id"], headers=auth_headers())
    assert deleted.status_code == 204
    assert_private(deleted)
    for endpoint in [path, path + "/revisions/1", path + "/revisions/2"]:
        missing = await client.get(endpoint, headers=auth_headers())
        assert missing.status_code == 404
        assert_private(missing)
    replay = await client.post(create_path(state, state["context"]), headers=auth_headers(), json=body)
    assert replay.status_code == 404
    assert_private(replay)
    with state["store"]._connect() as connection:
        for table in ["curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands", "curriculum_draft_documents"]:
            assert connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0


async def test_document_draft_http_strict_duplicate_json_does_not_consume_command(bound_document_api):
    client, state = bound_document_api
    body = documented_body(state)
    raw = json.dumps(body)[:-1] + ',"documentation_ids":[]}'
    response = await client.post(create_path(state, state["context"]), headers=auth_headers(), content=raw)
    assert response.status_code == 422
    assert_private(response)
    assert (await save_draft(client, state, body))["revision"] == 1
