"""Saved contexts use authenticated scope and copied, authoritative evidence."""

from copy import deepcopy
import json
import logging
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest

from app.config import Settings
from app.main import create_app
from app.models import ProjectCreate, TranscriptIngestRequest
from app.postgres import PostgresStore
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from conftest import MappingAuthenticator, TEST_TOKENS, auth_headers
from test_postgres_integration import isolated_postgres_url


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def context_api(isolated_postgres_url):
    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    service = TutorialService(
        store, DeterministicHashEmbeddingProvider(), EvidenceExtractiveAnswerProvider()
    )
    principal = TEST_TOKENS["tenant-a-token-long-enough"]
    project = service.create_project(principal, ProjectCreate(title="Synthetic curriculum API"))

    def seed_source(scoped_project, key="context-source-0001"):
        return service.ingest_transcript(
            principal,
            scoped_project.id,
            TranscriptIngestRequest(
                filename="synthetic-lesson.vtt",
                content=(
                    "WEBVTT\n\n"
                    "00:01.000 --> 00:04.000\n"
                    "create_app() exposes GET /health.\n\n"
                    "00:05.000 --> 00:09.000\n"
                    "A client checks the response status code.\n"
                ),
                authorization_mode="owner_upload",
                idempotency_key=key,
            ),
        ).source

    source = seed_source(project)
    app = create_app(
        settings=Settings(
            environment="test",
            store_backend="postgres",
            database_url=isolated_postgres_url,
            auto_migrate=False,
            development_auth_token="test-token-long-enough",
        ),
        store=store,
        authenticator=MappingAuthenticator(),
    )
    state = {
        "store": store,
        "service": service,
        "principal": principal,
        "project": project,
        "source": source,
        "seed_source": seed_source,
        "path": f"/api/v1/projects/{project.id}/curriculum/contexts",
    }
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, state


def context_body(state, key="context-request-0001"):
    return {
        "idempotency_key": key,
        "selected_sources": [
            {
                "source_id": str(state["source"].id),
                "generation": 1,
                "processing_version": state["source"].processing_version,
            }
        ],
        "learner": {
            "experience": "intermediate",
            "difficulty": "beginner",
            "language": "tr",
            "available_minutes": 90,
            "allow_prerequisites": False,
            "allow_extensions": False,
            "allow_external_documentation": False,
        },
    }


def assert_private(response):
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


async def create_context(client, state, body=None):
    response = await client.post(
        state["path"], headers=auth_headers(), json=body or context_body(state)
    )
    assert response.status_code == 201, response.text
    assert_private(response)
    return response.json()


async def test_context_http_persists_exact_authoritative_evidence_and_deletes(context_api):
    client, state = context_api
    body = context_body(state)
    saved = await create_context(client, state, body)
    project, source = state["project"], state["source"]
    assert saved["tenant_id"] == "tenant-a"
    assert saved["project_id"] == str(project.id)
    assert saved["request"]["learner"] == body["learner"]
    snapshot = saved["tutorial_snapshots"][0]
    assert snapshot["pin"] == {
        **body["selected_sources"][0],
        "tenant_id": "tenant-a",
        "project_id": str(project.id),
    }
    assert saved["request"]["selected_sources"] == [snapshot["pin"]]
    with state["store"]._connect() as connection:
        rows = connection.execute(
            "SELECT id,start_ms,end_ms,text,processing_version,generation FROM content_segments "
            "WHERE tenant_id=%s AND project_id=%s AND source_id=%s ORDER BY start_ms,end_ms,id",
            ("tenant-a", project.id, source.id),
        ).fetchall()
        # Legacy validation ingest has no processing_versions row; published
        # generation-one evidence remains a supported authoritative source.
        assert connection.execute(
            "SELECT count(*) AS count FROM processing_versions WHERE tenant_id=%s "
            "AND project_id=%s AND source_id=%s",
            ("tenant-a", project.id, source.id),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT count(*) AS count FROM curriculum_contexts "
            "WHERE tenant_id=%s AND project_id=%s",
            ("tenant-a", project.id),
        ).fetchone()["count"] == 1
    expected = [
        {
            "segment_id": str(row["id"]),
            "source_id": str(source.id),
            "source_filename": source.filename,
            "start_ms": row["start_ms"],
            "end_ms": row["end_ms"],
            "text": row["text"],
            "modality": "transcript",
            "processing_version": row["processing_version"],
            "generation": row["generation"],
            "asr_origin": None,
            "frame_id": None,
            "visual_origin": None,
        }
        for row in rows
    ]
    assert len(expected) == 2
    assert snapshot["segments"] == expected
    path = state["path"] + "/" + saved["id"]
    read = await client.get(path, headers=auth_headers())
    assert read.status_code == 200 and read.json() == saved
    assert_private(read)
    deleted = await client.delete(path, headers=auth_headers())
    assert deleted.status_code == 204 and not deleted.content
    assert_private(deleted)
    missing = await client.get(path, headers=auth_headers())
    assert missing.status_code == 404
    assert_private(missing)


async def test_context_http_replay_conflict_and_archive_are_consistent(context_api):
    client, state = context_api
    body = context_body(state)
    saved = await create_context(client, state, body)
    assert await create_context(client, state, body) == saved
    changed = deepcopy(body)
    changed["learner"]["available_minutes"] += 1
    conflict = await client.post(state["path"], headers=auth_headers(), json=changed)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert_private(conflict)
    state["service"].archive_project(state["principal"], state["project"].id)
    assert await create_context(client, state, body) == saved
    read = await client.get(state["path"] + "/" + saved["id"], headers=auth_headers())
    assert read.status_code == 200 and read.json() == saved
    blocked = await client.post(
        state["path"], headers=auth_headers(), json=context_body(state, "archived-new-context")
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "project_archived"
    assert_private(blocked)
    deleted = await client.delete(state["path"] + "/" + saved["id"], headers=auth_headers())
    assert deleted.status_code == 204
    assert_private(deleted)


async def test_context_http_all_operations_require_auth_and_exact_project_scope(context_api):
    client, state = context_api
    saved = await create_context(client, state)
    path = state["path"] + "/" + saved["id"]
    requests = [("POST", state["path"], context_body(state)), ("GET", path, None), ("DELETE", path, None)]
    for method, endpoint, body in requests:
        response = await client.request(method, endpoint, json=body)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert_private(response)
        foreign = await client.request(method, endpoint, headers=auth_headers("tenant-b"), json=body)
        assert foreign.status_code == 404
        assert_private(foreign)
    other = state["service"].create_project(state["principal"], ProjectCreate(title="Other project"))
    foreign_context = f"/api/v1/projects/{other.id}/curriculum/contexts/{saved['id']}"
    for method in ["GET", "DELETE"]:
        response = await client.request(method, foreign_context, headers=auth_headers())
        assert response.status_code == 404
        assert_private(response)
    assert (await client.get(path, headers=auth_headers())).json() == saved


async def test_context_http_rechecks_membership_after_identity_mapping(context_api, monkeypatch):
    client, state = context_api
    saved = await create_context(client, state)
    original = state["store"].bootstrap_principal

    def revoked_after_mapping(principal):
        actor = original(principal)
        with state["store"]._connect() as connection:
            connection.execute(
                "DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s",
                (principal.tenant_id, actor),
            )
        return actor

    monkeypatch.setattr(state["store"], "bootstrap_principal", revoked_after_mapping)
    for method, path, body in [
        ("POST", state["path"], context_body(state, "revoked-membership-key")),
        ("GET", state["path"] + "/" + saved["id"], None),
        ("DELETE", state["path"] + "/" + saved["id"], None),
    ]:
        response = await client.request(method, path, headers=auth_headers(), json=body)
        assert response.status_code == 404
        assert_private(response)


async def test_context_http_rejects_missing_foreign_and_forged_source_pins(context_api):
    client, state = context_api
    other_project = state["service"].create_project(state["principal"], ProjectCreate(title="Foreign lesson"))
    other_source = state["seed_source"](other_project, "other-project-lesson")
    cases = [{"source_id": str(uuid4())}, {"source_id": str(other_source.id)},
             {"generation": 2}, {"processing_version": "forged-private-parser-text"}]
    for index, changes in enumerate(cases):
        body = context_body(state, f"unavailable-context-{index}")
        body["selected_sources"][0].update(changes)
        response = await client.post(state["path"], headers=auth_headers(), json=body)
        assert response.status_code == 409
        assert response.json() == {
            "code": "curriculum_source_unavailable",
            "detail": "Choose a published source generation with matching evidence.",
        }
        assert "forged-private-parser-text" not in response.text
        assert_private(response)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM curriculum_contexts").fetchone()["count"] == 0


async def test_context_http_rejects_unpublished_source_before_snapshotting(context_api):
    client, state = context_api
    with state["store"]._connect() as connection:
        connection.execute(
            "UPDATE sources SET active_generation=NULL,status='created' WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, state["source"].id),
        )
    response = await client.post(state["path"], headers=auth_headers(), json=context_body(state))
    assert response.status_code == 409 and response.json()["code"] == "curriculum_source_unavailable"
    assert_private(response)


@pytest.mark.parametrize("overflow", ["segments", "characters"])
async def test_context_http_rejects_entire_oversized_evidence_without_truncation(context_api, overflow):
    client, state = context_api
    with state["store"]._connect() as connection:
        original = connection.execute(
            "SELECT id FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s LIMIT 1",
            ("tenant-a", state["project"].id, state["source"].id),
        ).fetchone()["id"]
        additional = 499 if overflow == "segments" else 49
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO content_segments "
                "(id,tenant_id,project_id,source_id,modality,start_ms,end_ms,text,embedding,processing_version,generation) "
                "SELECT %s,tenant_id,project_id,source_id,modality,start_ms,end_ms,text,embedding,processing_version,generation "
                "FROM content_segments WHERE tenant_id=%s AND project_id=%s AND id=%s",
                [(uuid4(), "tenant-a", state["project"].id, original) for _ in range(additional)],
            )
        if overflow == "characters":
            connection.execute(
                "UPDATE content_segments SET text=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s",
                ("x" * 10_000, "tenant-a", state["project"].id, state["source"].id),
            )
    response = await client.post(state["path"], headers=auth_headers(), json=context_body(state))
    assert response.status_code == 422
    assert response.json()["code"] == "curriculum_evidence_too_large"
    assert_private(response)
    with state["store"]._connect() as connection:
        for table in ["curriculum_contexts", "curriculum_context_sources"]:
            assert connection.execute(
                f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
                ("tenant-a", state["project"].id),
            ).fetchone()["count"] == 0


async def test_context_http_does_not_accept_scope_evidence_or_implicit_preferences(context_api):
    client, state = context_api
    base = context_body(state)
    cases = []
    for key, value in [
        ("tenant_id", "tenant-b"), ("project_id", str(uuid4())),
        ("tutorial_snapshots", [{"text": "private-model-text"}]),
        ("documentation_snapshots", [{"url": "http://private.invalid"}]),
    ]:
        body = deepcopy(base)
        body[key] = value
        cases.append(body)
    for key, value in [("generation", True), ("generation", "1"), ("generation", 0),
                       ("source_id", "not-a-uuid"), ("processing_version", 123),
                       ("segment_ids", [str(uuid4())]), ("tenant_id", "tenant-b")]:
        body = deepcopy(base)
        body["selected_sources"][0][key] = value
        cases.append(body)
    for key, value in [("allow_extensions", "false"), ("allow_prerequisites", 0),
                       ("available_minutes", "90"), ("available_minutes", True),
                       ("private_token", "private-model-text")]:
        body = deepcopy(base)
        body["learner"][key] = value
        cases.append(body)
    body = deepcopy(base)
    del body["learner"]["allow_external_documentation"]
    cases.append(body)
    body = deepcopy(base)
    body["selected_sources"].append(body["selected_sources"][0].copy())
    cases.append(body)
    for body in cases:
        response = await client.post(state["path"], headers=auth_headers(), json=body)
        assert response.status_code == 422, response.text
        assert response.json() == {"code": "validation_error", "detail": "Request validation failed."}
        assert "private-model-text" not in response.text
        assert_private(response)
    with state["store"]._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM curriculum_contexts").fetchone()["count"] == 0


async def test_context_http_rejects_ambiguous_raw_json_without_echoing_input(context_api):
    client, state = context_api
    raw = json.dumps(context_body(state))
    cases = [
        raw.replace('"allow_extensions": false', '"allow_extensions": false, "allow_extensions": true'),
        raw.replace('"available_minutes": 90', '"available_minutes": NaN'),
        raw[:-1] + ', "idempotency_key": "ambiguous-private-key"}',
        '{"private-secret": "unterminated',
    ]
    for payload in cases:
        response = await client.post(
            state["path"], headers={**auth_headers(), "Content-Type": "application/json"}, content=payload
        )
        assert response.status_code == 422
        assert response.json() == {"code": "validation_error", "detail": "Request validation failed."}
        assert "private" not in response.text
        assert_private(response)


async def test_context_http_oversize_and_unknown_routes_still_return_private_responses(context_api):
    client, state = context_api
    oversized = await client.post(state["path"], headers=auth_headers(), content=b"x" * 16_385)
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "curriculum_request_too_large"
    assert_private(oversized)
    unauthenticated = await client.post(state["path"], content=b"x" * 16_385)
    assert unauthenticated.status_code == 401
    assert_private(unauthenticated)
    for method in ["GET", "DELETE"]:
        missing = await client.request(method, state["path"] + "/" + str(uuid4()), headers=auth_headers())
        assert missing.status_code == 404
        assert_private(missing)


async def test_context_http_copy_survives_later_publication_and_source_label_change(context_api):
    client, state = context_api
    body = context_body(state)
    saved = await create_context(client, state, body)
    with state["store"]._connect() as connection:
        connection.execute(
            "UPDATE sources SET active_generation=2,processing_version='later-parser:g2',filename='renamed.vtt' "
            "WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, state["source"].id),
        )
    read = await client.get(state["path"] + "/" + saved["id"], headers=auth_headers())
    assert read.status_code == 200 and read.json() == saved
    assert await create_context(client, state, body) == saved
    # A new context may deliberately select the retained older generation.
    retained = await create_context(client, state, context_body(state, "retained-old-generation"))
    assert retained["request"] == saved["request"]
    assert retained["tutorial_snapshots"][0]["pin"]["generation"] == 1
    assert {segment["segment_id"] for segment in retained["tutorial_snapshots"][0]["segments"]} == {
        segment["segment_id"] for segment in saved["tutorial_snapshots"][0]["segments"]
    }


async def test_context_http_source_delete_removes_copied_text_and_replay(context_api):
    client, state = context_api
    body = context_body(state)
    saved = await create_context(client, state, body)
    with state["store"]._connect() as connection:
        connection.execute(
            "DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, state["source"].id),
        )
        for table in ["curriculum_contexts", "curriculum_context_sources"]:
            assert connection.execute(
                f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
                ("tenant-a", state["project"].id),
            ).fetchone()["count"] == 0
    read = await client.get(state["path"] + "/" + saved["id"], headers=auth_headers())
    assert read.status_code == 404
    replay = await client.post(state["path"], headers=auth_headers(), json=body)
    assert replay.status_code == 409 and replay.json()["code"] == "curriculum_source_unavailable"
    assert_private(replay)


async def test_context_http_project_delete_removes_contexts_and_dependencies(context_api):
    client, state = context_api
    saved = await create_context(client, state)
    deleted = await client.delete(f"/api/v1/projects/{state['project'].id}", headers=auth_headers())
    assert deleted.status_code == 204
    with state["store"]._connect() as connection:
        for table in ["curriculum_contexts", "curriculum_context_sources"]:
            assert connection.execute(
                f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
                ("tenant-a", state["project"].id),
            ).fetchone()["count"] == 0
    for method in ["GET", "DELETE"]:
        response = await client.request(method, state["path"] + "/" + saved["id"], headers=auth_headers())
        assert response.status_code == 404
        assert_private(response)


async def test_context_http_logs_and_metrics_omit_private_request_and_evidence(context_api, caplog):
    client, state = context_api
    caplog.set_level(logging.INFO, logger="tutorial_workspace")
    body = context_body(state, "private-context-idempotency-key")
    saved = await create_context(client, state, body)
    with state["store"]._connect() as connection:
        assert connection.execute(
            "SELECT id FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
            ("tenant-a", state["project"].id, UUID(saved["id"])),
        ).fetchone()
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert '/api/v1/projects/{project_id}/curriculum/contexts' in metrics.text
    emitted = "\n".join(record.getMessage() for record in caplog.records) + metrics.text
    for private in [body["idempotency_key"], "synthetic-lesson.vtt", "create_app() exposes GET /health.",
                    "tenant-a-token-long-enough"]:
        assert private not in emitted
    committed = [json.loads(record.getMessage()) for record in caplog.records
                 if '"event": "curriculum_context_committed"' in record.getMessage()]
    assert len(committed) == 1
    assert committed[0]["context_id"] == saved["id"]
    assert committed[0]["source_count"] == 1 and committed[0]["segment_count"] == 2
