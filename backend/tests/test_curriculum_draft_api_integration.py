"""Editable assignment drafts keep scoped history and authoritative evidence."""

from copy import deepcopy
import json
import logging
from uuid import UUID, uuid4

import pytest

from app.models import ProjectCreate
from conftest import auth_headers
from test_curriculum_api_integration import (
    assert_private,
    context_api,
    context_body,
    create_context,
)
from test_postgres_integration import isolated_postgres_url


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def draft_body(context, key="draft-create-request-0001"):
    segment = context["tutorial_snapshots"][0]["segments"][0]["segment_id"]
    return {
        "idempotency_key": key,
        "content": {
            "schema_version": "assignment-draft-v1",
            "title": "Synthetic health endpoint exercise",
            "scenario": "Implement a health endpoint described by the selected tutorial.",
            "estimated_minutes": 45,
            "objectives": [{"id": "health", "description": "Expose a health route.",
                            "tutorial_segment_ids": [segment]}],
            "requirements": [{"id": "route", "label": "covered", "description": "Expose GET /health.",
                              "objective_ids": ["health"], "tutorial_segment_ids": [segment],
                              "documentation_excerpt_ids": []}],
            "constraints": ["Use the tutorial's application structure."],
            "deliverables": ["Application source code."],
            "acceptance_criteria": [{"id": "responds", "description": "GET /health responds successfully.",
                                     "requirement_ids": ["route"]}],
            "rubric": [{"id": "behavior", "description": "The health route meets the stated criterion.",
                        "acceptance_criterion_ids": ["responds"]}],
            "hints": [{"id": "route_hint", "level": 1, "text": "Find the route registration in the evidence.",
                       "requirement_ids": ["route"]}],
        },
    }


def create_path(state, context):
    return state["path"] + "/" + context["id"] + "/drafts"


def draft_path(state, draft_id):
    return f"/api/v1/projects/{state['project'].id}/curriculum/drafts/{draft_id}"


async def create_draft(client, state, context, body=None):
    response = await client.post(
        create_path(state, context), headers=auth_headers(), json=body or draft_body(context)
    )
    assert response.status_code == 201, response.text
    assert_private(response)
    return response.json()


def replacement(body, revision=1, key="draft-replace-request-0001"):
    result = deepcopy(body)
    result["idempotency_key"] = key
    result["expected_revision"] = revision
    result["content"]["title"] = "Revised synthetic health exercise"
    return result


async def test_draft_http_create_edit_and_history_bind_only_cited_evidence(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    first = await create_draft(client, state, context, body)
    assert set(first) == {"id", "tenant_id", "project_id", "context_id", "revision", "created_at", "assignment", "documentation_ids"}
    assert first["documentation_ids"] == []
    assert first["tenant_id"] == "tenant-a"
    assert first["project_id"] == str(state["project"].id)
    assert first["context_id"] == context["id"] and first["revision"] == 1
    assignment = first["assignment"]
    assert assignment["tenant_id"] == "tenant-a"
    assert assignment["project_id"] == str(state["project"].id)
    assert assignment["draft"] == {
        **body["content"], "tenant_id": "tenant-a", "project_id": str(state["project"].id)
    }
    assert assignment["documentation_snapshots"] == []
    assert assignment["tutorial_evidence"] == context["tutorial_snapshots"][0]["segments"][:1]
    assert len(context["tutorial_snapshots"][0]["segments"]) == 2

    path = draft_path(state, first["id"])
    update = replacement(body)
    response = await client.put(path, headers=auth_headers(), json=update)
    assert response.status_code == 200, response.text
    assert_private(response)
    second = response.json()
    assert second["id"] == first["id"] and second["revision"] == 2
    assert second["assignment"]["draft"]["title"] == update["content"]["title"]
    for endpoint, expected in [(path, second), (path + "/revisions/1", first), (path + "/revisions/2", second)]:
        read = await client.get(endpoint, headers=auth_headers())
        assert read.status_code == 200 and read.json() == expected
        assert_private(read)


async def test_draft_http_replays_exact_historical_result_after_edits_and_archive(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    first = await create_draft(client, state, context, body)
    path = draft_path(state, first["id"])
    update = replacement(body)
    second = (await client.put(path, headers=auth_headers(), json=update)).json()
    third_body = replacement(body, revision=2, key="draft-replace-request-0002")
    third_body["content"]["title"] = "Third synthetic revision"
    third = await client.put(path, headers=auth_headers(), json=third_body)
    assert third.status_code == 200 and third.json()["revision"] == 3
    state["service"].archive_project(state["principal"], state["project"].id)
    assert await create_draft(client, state, context, body) == first
    replay = await client.put(path, headers=auth_headers(), json=update)
    assert replay.status_code == 200 and replay.json() == second
    assert_private(replay)
    latest = await client.get(path, headers=auth_headers())
    assert latest.status_code == 200 and latest.json() == third.json()
    assert_private(latest)
    for method, endpoint, payload in [
        ("POST", create_path(state, context), draft_body(context, "archived-new-draft")),
        ("PUT", path, replacement(body, revision=3, key="archived-new-revision")),
    ]:
        blocked = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert blocked.status_code == 409 and blocked.json()["code"] == "project_archived"
        assert_private(blocked)
    deleted = await client.delete(path, headers=auth_headers())
    assert deleted.status_code == 204 and not deleted.content
    assert_private(deleted)


async def test_draft_http_idempotency_includes_content_operation_target_and_expected_revision(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    first = await create_draft(client, state, context, body)
    second_context = await create_context(client, state, context_body(state, "another-context-request"))
    second = await create_draft(client, state, context, draft_body(context, "another-draft-request"))
    path = draft_path(state, first["id"])
    changed = deepcopy(body)
    changed["content"]["title"] = "Changed private content"
    update = replacement(body)
    accepted = await client.put(path, headers=auth_headers(), json=update)
    assert accepted.status_code == 200
    changed_update = deepcopy(update)
    changed_update["expected_revision"] = 2
    for method, endpoint, payload in [
        ("POST", create_path(state, context), changed),
        ("POST", create_path(state, second_context), body),
        ("PUT", path, replacement(body, key=body["idempotency_key"])),
        ("PUT", path, changed_update),
        ("PUT", draft_path(state, second["id"]), update),
    ]:
        conflict = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
        assert "private content" not in conflict.text
        assert_private(conflict)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM curriculum_draft_commands").fetchone()["count"] == 3


async def test_draft_http_stale_edit_does_not_append_or_consume_command_key(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    first = await create_draft(client, state, context, body)
    path = draft_path(state, first["id"])
    assert (await client.put(path, headers=auth_headers(), json=replacement(body))).status_code == 200
    stale = replacement(body, key="retry-after-stale-edit")
    response = await client.put(path, headers=auth_headers(), json=stale)
    assert response.status_code == 409 and response.json()["code"] == "draft_revision_conflict"
    assert_private(response)
    stale["expected_revision"] = 2
    retry = await client.put(path, headers=auth_headers(), json=stale)
    assert retry.status_code == 200 and retry.json()["revision"] == 3
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM curriculum_draft_revisions").fetchone()["count"] == 3
        assert connection.execute("SELECT count(*) AS count FROM curriculum_draft_commands").fetchone()["count"] == 3


async def test_draft_http_all_operations_require_authentication_and_exact_project_scope(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    path = draft_path(state, saved["id"])
    requests = [("POST", create_path(state, context), body), ("GET", path, None),
                ("GET", path + "/revisions/1", None), ("PUT", path, replacement(body)), ("DELETE", path, None)]
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Unrelated draft project"))
    for method, endpoint, payload in requests:
        missing_auth = await client.request(method, endpoint, json=payload)
        assert missing_auth.status_code == 401
        assert missing_auth.headers["www-authenticate"] == "Bearer"
        assert_private(missing_auth)
        foreign_tenant = await client.request(method, endpoint, headers=auth_headers("tenant-b"), json=payload)
        assert foreign_tenant.status_code == 404
        assert_private(foreign_tenant)
        foreign_project = await client.request(
            method, endpoint.replace(str(state["project"].id), str(other.id)), headers=auth_headers(), json=payload
        )
        assert foreign_project.status_code == 404
        assert_private(foreign_project)
    assert (await client.get(path, headers=auth_headers())).json() == saved


async def test_draft_http_rechecks_membership_after_identity_mapping(context_api, monkeypatch):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    original = state["store"].bootstrap_principal

    def revoked_after_mapping(principal):
        actor = original(principal)
        with state["store"]._connect() as connection:
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
        return actor

    monkeypatch.setattr(state["store"], "bootstrap_principal", revoked_after_mapping)
    path = draft_path(state, saved["id"])
    for method, endpoint, payload in [
        ("POST", create_path(state, context), body), ("GET", path, None),
        ("GET", path + "/revisions/1", None), ("PUT", path, replacement(body)), ("DELETE", path, None),
    ]:
        response = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)


async def test_draft_http_rejects_client_scope_evidence_metadata_unknown_fields_and_coercions(context_api):
    client, state = context_api
    context = await create_context(client, state)
    base = draft_body(context)
    cases = []
    for key, value in [("tenant_id", "tenant-b"), ("project_id", str(uuid4())),
                       ("tutorial_evidence", [{"text": "private-source-payload"}]),
                       ("documentation_snapshots", [{"url": "https://private.invalid"}])]:
        body = deepcopy(base)
        body[key] = value
        cases.append(body)
        body = deepcopy(base)
        body["content"][key] = value
        cases.append(body)
    for key, value in [("estimated_minutes", True), ("estimated_minutes", "45"),
                       ("title", 100), ("schema_version", "unsupported-private-schema")]:
        body = deepcopy(base)
        body["content"][key] = value
        cases.append(body)
    for changes in [{"tutorial_segment_ids": ["not-a-uuid"]}, {"objective_ids": ["missing"]},
                    {"tutorial_segment_ids": []}, {"source_filename": "private-source-payload"}]:
        body = deepcopy(base)
        body["content"]["requirements"][0].update(changes)
        cases.append(body)
    body = deepcopy(base)
    body["content"]["hints"][0]["level"] = True
    cases.append(body)
    body = deepcopy(base)
    body["content"]["rubric"] = []
    cases.append(body)
    for body in cases:
        response = await client.post(create_path(state, context), headers=auth_headers(), json=body)
        assert response.status_code == 422, response.text
        assert response.json() == {"code": "validation_error", "detail": "Request validation failed."}
        assert "private" not in response.text
        assert_private(response)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM curriculum_drafts").fetchone()["count"] == 0


async def test_draft_http_binds_saved_context_and_rejects_unsupported_evidence_or_effort(context_api):
    client, state = context_api
    context = await create_context(client, state)
    base = draft_body(context)
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Other source context"))
    source = state["seed_source"](other, "unrelated-source-request")
    with state["store"]._connect() as connection:
        foreign_segment = str(connection.execute(
            "SELECT id FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s LIMIT 1",
            ("tenant-a", other.id, source.id),
        ).fetchone()["id"])
    cases = []
    for segment in [str(uuid4()), foreign_segment]:
        body = deepcopy(base)
        body["content"]["objectives"][0]["tutorial_segment_ids"] = [segment]
        cases.append(body)
    body = deepcopy(base)
    body["content"]["estimated_minutes"] = 91
    cases.append(body)
    body = deepcopy(base)
    body["content"]["title"] = "private-title\x00"
    cases.append(body)
    body = deepcopy(base)
    body["content"]["requirements"][0].update({"label": "extension", "documentation_excerpt_ids": [str(uuid4())]})
    cases.append(body)
    for body in cases:
        response = await client.post(create_path(state, context), headers=auth_headers(), json=body)
        assert response.status_code == 422, response.text
        assert response.json() == {"code": "invalid_curriculum_draft", "detail": "The assignment draft could not be validated."}
        assert "private" not in response.text
        assert_private(response)
    # Failed input cannot leave a partial draft or reserve the shared retry key.
    saved = await create_draft(client, state, context, base)
    assert saved["revision"] == 1
    invalid_edit = replacement(base)
    invalid_edit["content"]["requirements"][0]["tutorial_segment_ids"] = [str(uuid4())]
    rejected = await client.put(draft_path(state, saved["id"]), headers=auth_headers(), json=invalid_edit)
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_curriculum_draft"
    assert_private(rejected)
    assert (await client.get(draft_path(state, saved["id"]), headers=auth_headers())).json() == saved
    with state["store"]._connect() as connection:
        for table in ["curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands"]:
            assert connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"] == 1


async def test_draft_http_put_expected_revision_is_required_and_strict(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    path = draft_path(state, saved["id"])
    for value in [None, True, "1", 0, -1, 2_147_483_647]:
        payload = replacement(body)
        if value is None:
            del payload["expected_revision"]
        else:
            payload["expected_revision"] = value
        response = await client.put(path, headers=auth_headers(), json=payload)
        assert response.status_code == 422 and response.json()["code"] == "validation_error"
        assert_private(response)
    assert (await client.get(path, headers=auth_headers())).json() == saved


async def test_draft_http_missing_targets_and_bounded_revision_paths(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    missing_path = draft_path(state, str(uuid4()))
    for method, endpoint, payload in [
        ("POST", create_path(state, {"id": str(uuid4())}), draft_body(context, "missing-context-key")),
        ("GET", missing_path, None), ("GET", missing_path + "/revisions/1", None),
        ("PUT", missing_path, replacement(body)), ("DELETE", missing_path, None),
        ("GET", draft_path(state, saved["id"]) + "/revisions/2", None),
        ("GET", draft_path(state, saved["id"]) + "/revisions/2147483647", None),
    ]:
        response = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)
    for value in ["0", "-1", "true", "1.5", "2147483648"]:
        response = await client.get(draft_path(state, saved["id"]) + "/revisions/" + value, headers=auth_headers())
        assert response.status_code == 422 and response.json()["code"] == "validation_error"
        assert_private(response)


async def test_draft_http_saved_evidence_survives_later_publication_and_label_change(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    with state["store"]._connect() as connection:
        connection.execute(
            "UPDATE sources SET active_generation=2,processing_version='later-parser:g2',filename='renamed.vtt' "
            "WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, state["source"].id),
        )
    path = draft_path(state, saved["id"])
    assert (await client.get(path, headers=auth_headers())).json() == saved
    assert await create_draft(client, state, context, body) == saved
    updated = await client.put(path, headers=auth_headers(), json=replacement(body))
    assert updated.status_code == 200
    assert updated.json()["assignment"]["tutorial_evidence"] == saved["assignment"]["tutorial_evidence"]
    assert updated.json()["assignment"]["tutorial_evidence"][0]["generation"] == 1
    historical = await client.get(path + "/revisions/1", headers=auth_headers())
    assert historical.status_code == 200 and historical.json() == saved
    assert_private(historical)


async def test_draft_http_delete_removes_all_revisions_and_replay_receipts(context_api):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    path = draft_path(state, saved["id"])
    assert (await client.put(path, headers=auth_headers(), json=replacement(body))).status_code == 200
    deleted = await client.delete(path, headers=auth_headers())
    assert deleted.status_code == 204 and not deleted.content
    assert_private(deleted)
    for endpoint in [path, path + "/revisions/1", path + "/revisions/2"]:
        read = await client.get(endpoint, headers=auth_headers())
        assert read.status_code == 404
        assert_private(read)
    with state["store"]._connect() as connection:
        for table in ["curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands"]:
            assert connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"] == 0
    # The preserved context permits a fresh draft; deleted content is not replayed.
    recreated = await create_draft(client, state, context, body)
    assert recreated["id"] != saved["id"] and recreated["revision"] == 1


@pytest.mark.parametrize("deleted_kind", ["context", "source", "project"])
async def test_draft_http_parent_deletion_cascades_content_history_and_receipts(context_api, deleted_kind):
    client, state = context_api
    context = await create_context(client, state)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    path = draft_path(state, saved["id"])
    assert (await client.put(path, headers=auth_headers(), json=replacement(body))).status_code == 200
    if deleted_kind == "context":
        deleted = await client.delete(state["path"] + "/" + context["id"], headers=auth_headers())
    elif deleted_kind == "source":
        # The shared API fixture has no object store. Exercise the same source
        # deletion trigger directly, then verify every draft HTTP view is gone.
        with state["store"]._connect() as connection:
            connection.execute(
                "DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                ("tenant-a", state["project"].id, state["source"].id),
            )
    else:
        deleted = await client.delete(f"/api/v1/projects/{state['project'].id}", headers=auth_headers())
    if deleted_kind != "source":
        assert deleted.status_code == 204, deleted.text
    with state["store"]._connect() as connection:
        for table in ["curriculum_contexts", "curriculum_context_sources", "curriculum_drafts",
                      "curriculum_draft_revisions", "curriculum_draft_commands"]:
            assert connection.execute(
                f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
                ("tenant-a", state["project"].id),
            ).fetchone()["count"] == 0
    for method, endpoint, payload in [
        ("GET", path, None), ("GET", path + "/revisions/1", None), ("DELETE", path, None),
        ("PUT", path, replacement(body)), ("POST", create_path(state, context), body),
    ]:
        response = await client.request(method, endpoint, headers=auth_headers(), json=payload)
        assert response.status_code == 404
        assert_private(response)


async def test_draft_http_logs_and_metrics_keep_private_content_and_retry_keys_out(context_api, caplog):
    client, state = context_api
    caplog.set_level(logging.INFO, logger="tutorial_workspace")
    context = await create_context(client, state)
    body = draft_body(context, "private-draft-retry-key")
    body["content"]["title"] = "Private synthetic learner draft"
    saved = await create_draft(client, state, context, body)
    path = draft_path(state, saved["id"])
    assert await create_draft(client, state, context, body) == saved
    update = replacement(body, key="private-draft-edit-key")
    revised = await client.put(path, headers=auth_headers(), json=update)
    assert revised.status_code == 200
    assert (await client.delete(path, headers=auth_headers())).status_code == 204
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert '/api/v1/projects/{project_id}/curriculum/contexts/{context_id}/drafts' in metrics.text
    emitted = "\n".join(record.getMessage() for record in caplog.records) + metrics.text
    for private in [body["idempotency_key"], update["idempotency_key"], body["content"]["title"],
                    body["content"]["scenario"], "synthetic-lesson.vtt", "create_app() exposes GET /health.",
                    "tenant-a-token-long-enough"]:
        assert private not in emitted
    events = [json.loads(record.getMessage()) for record in caplog.records
              if '"event": "curriculum_draft_' in record.getMessage()]
    assert [event["event"] for event in events] == [
        "curriculum_draft_created", "curriculum_draft_revised", "curriculum_draft_deleted"
    ]
    assert all(event["draft_id"] == saved["id"] for event in events)
    assert events[0]["revision"] == 1 and events[1]["revision"] == 2
    assert events[0]["objective_count"] == 1 and events[0]["requirement_count"] == 1
    with state["store"]._connect() as connection:
        assert connection.execute(
            "SELECT id FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, UUID(context["id"])),
        ).fetchone()
