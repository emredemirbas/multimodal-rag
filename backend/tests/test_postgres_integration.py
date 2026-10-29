from __future__ import annotations

import os
import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.models import (
    AuthenticatedPrincipal,
    ProjectCreate,
    ProjectListStatus,
    ProjectUpdate,
    TranscriptIngestRequest,
)
from app.postgres import PostgresStore
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService


def configured_database_url() -> str | None:
    explicit_url = os.getenv("TEST_DATABASE_URL")
    if explicit_url:
        return explicit_url
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        return None
    return make_conninfo(
        host=os.getenv("TEST_POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "tutorial"),
        user=os.getenv("POSTGRES_USER", "tutorial"),
        password=password,
    )


DATABASE_URL = configured_database_url()


@pytest.fixture
def isolated_postgres_url():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    schema = f"sprint1_test_{uuid4().hex}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield make_conninfo(DATABASE_URL, options=f"-csearch_path={schema},public")
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def install_before(database_url, cutoff):
    migrations = Path(__file__).resolve().parents[1] / "app/migrations"
    with psycopg.connect(database_url) as connection:
        connection.execute("CREATE TABLE schema_migrations (version text PRIMARY KEY, sha256 text)")
        for migration in sorted(migrations.glob("*.sql")):
            if migration.name >= cutoff:
                break
            script = migration.read_text()
            connection.execute(script)
            connection.execute("INSERT INTO schema_migrations (version,sha256) VALUES (%s,%s)",
                               (migration.name, sha256(script.encode()).hexdigest()))


@pytest.mark.integration
@pytest.mark.parametrize("cutoff", ["0020_curriculum_contexts.sql", "0021_curriculum_drafts.sql", "0022_curriculum_runs.sql", "0023_curriculum_delivery.sql", "0024_curriculum_request_identity.sql"])
def test_curriculum_upgrade_preserves_existing_rag_sources(isolated_postgres_url, cutoff):
    """Upgrade populated RAG/context/draft databases, rather than only fresh schemas."""
    from app.curriculum.persistence import ContextCreate
    from app.curriculum.repository import ContextRepository

    install_before(isolated_postgres_url, cutoff)
    store = PostgresStore(isolated_postgres_url)
    service = TutorialService(store, DeterministicHashEmbeddingProvider(), EvidenceExtractiveAnswerProvider())
    principal = AuthenticatedPrincipal(provider="test", subject="curriculum-upgrade", tenant_id="upgrade-rag")
    project = service.create_project(principal, ProjectCreate(title="Existing RAG workspace"))
    source = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(
        filename="upgrade.vtt", authorization_mode="owner_upload", idempotency_key="pre-curriculum-source",
        content="WEBVTT\n\n00:01.000 --> 00:05.000\nGET /health reports service availability.\n",
    )).source
    before = service.ask(principal, project.id, "GET /health")
    assert not before.abstained
    repository = ContextRepository(store)
    actor = store.bootstrap_principal(principal)
    body = ContextCreate(
        idempotency_key="post-upgrade-context",
        selected_sources=[{"source_id": source.id, "generation": 1, "processing_version": source.processing_version}],
        learner={"experience": "intermediate", "difficulty": "beginner", "language": "en",
                 "available_minutes": 60, "allow_prerequisites": False, "allow_extensions": False,
                 "allow_external_documentation": False},
    )
    existing = repository.create(principal.tenant_id, project.id, actor, body) if cutoff > "0020_curriculum_contexts.sql" else None
    previous_draft = None
    if cutoff >= "0022_curriculum_runs.sql":
        from app.curriculum.drafts import DraftRepository
        from app.curriculum.persistence import DraftCreate, DraftReplace
        from test_curriculum_drafts_integration import content_for
        drafts = DraftRepository(store)
        draft_body = DraftCreate(idempotency_key="pre-runs-draft", content=content_for(existing))
        first_draft = drafts.create(principal.tenant_id, project.id, actor, existing.id, draft_body)
        previous_draft = drafts.replace(principal.tenant_id, project.id, actor, first_draft.id, DraftReplace(
            idempotency_key="pre-runs-edit", expected_revision=1, content=content_for(existing, title="Before runs upgrade")))
    run_tables = ("curriculum_runs", "curriculum_run_attempts", "curriculum_run_outbox",
                  "curriculum_run_commands", "curriculum_run_checkpoints", "curriculum_model_calls")
    previous_runs = {}
    if cutoff >= "0023_curriculum_delivery.sql":
        from app.curriculum.run_contracts import ModelCallStart, RunClaim, RunCreate
        from app.curriculum.runs import RunRepository
        run = RunRepository(store).create(principal.tenant_id, project.id, actor, existing.id,
                                         RunCreate(idempotency_key="pre-delivery-run", workflow_version="upgrade-probe-v1"))
        token = uuid4()
        scope = (principal.tenant_id, project.id, run.id)
        # Seed the historical schema directly: current claim/progress reads
        # correctly require the result relation added by the deployment migration.
        payload = {"accepted": "Synthetic saved stage"}
        historical_start = ModelCallStart(call_id=uuid4(), purpose="upgrade-probe", provider="ollama-local",
            model="fixture-model", model_digest="a"*64, engine="fixture-engine", prompt_version="fixture-prompt",
            input_characters=12, input_tokens=None)
        historical_hash = sha256(json.dumps(historical_start.model_dump(mode="json",
            exclude={"input_sha256", "schema_version", "request_version"}), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with store._connect() as connection:
            connection.execute("""UPDATE curriculum_runs SET status='running',attempt_count=1,checkpoint_seq=1,
                lease_token=%s,lease_expires_at=clock_timestamp()+interval '180 seconds'
                WHERE tenant_id=%s AND project_id=%s AND id=%s""", (token, *scope))
            connection.execute("""INSERT INTO curriculum_run_attempts
                (tenant_id,project_id,run_id,attempt_number,lease_token) VALUES (%s,%s,%s,1,%s)""", (*scope, token))
            connection.execute("""INSERT INTO curriculum_run_checkpoints
                (tenant_id,project_id,run_id,sequence,attempt_number,stage,workflow_version,payload,content_sha256)
                VALUES (%s,%s,%s,1,1,'saved-stage','upgrade-probe-v1',%s,%s)""",
                (*scope, Jsonb(payload), sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()))
            connection.execute("""INSERT INTO curriculum_model_calls
                (tenant_id,project_id,run_id,call_id,attempt_number,purpose,provider,model,model_digest,
                 request_sha256,engine,prompt_version,input_characters,input_tokens)
                VALUES (%s,%s,%s,%s,1,'upgrade-probe','ollama-local','fixture-model',%s,%s,'fixture-engine','fixture-prompt',12,NULL)""",
                (*scope, historical_start.call_id, "a"*64, historical_hash))
            previous_runs = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in run_tables}
    store.run_migrations()
    store.run_migrations()
    after = service.ask(principal, project.id, "GET /health")
    assert after.answer == before.answer and after.citations == before.citations
    saved = repository.create(principal.tenant_id, project.id, actor, body)
    if existing is not None:
        assert saved == existing
    assert saved.tutorial_snapshots[0].segments[0].segment_id == after.citations[0].segment_id
    assert repository.read(principal.tenant_id, project.id, actor, saved.id) == saved
    if previous_draft is not None:
        assert drafts.read(principal.tenant_id, project.id, actor, previous_draft.id) == previous_draft
        assert drafts.create(principal.tenant_id, project.id, actor, existing.id, draft_body) == first_draft
    with store._connect() as connection:
        for table in ("curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands"):
            expected = (1 if table == "curriculum_drafts" else 2) if previous_draft is not None else 0
            assert connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"] == expected
        for table in run_tables:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            expected = previous_runs.get(table, [])
            assert [{key: row[key] for key in before} for row, before in zip(rows, expected)] == expected
            assert len(rows) == len(expected)
            if table == "curriculum_model_calls":
                assert all(row["input_sha256"] is row["schema_version"] is row["request_version"] is None for row in rows)
        assert connection.execute("SELECT count(*) AS count FROM curriculum_run_results").fetchone()["count"] == 0
    if previous_runs:
        from app.curriculum.run_progress import RunProgressRepository
        claim = RunClaim(tenant_id=principal.tenant_id, project_id=project.id, run_id=run.id,
                         lease_token=token, attempt_number=1)
        replay = RunProgressRepository(store).begin_call(claim, historical_start)
        assert replay.status == "started" and replay.call_id == historical_start.call_id
        assert replay.created_at == previous_runs["curriculum_model_calls"][0]["created_at"]
        assert replay.input_sha256 is replay.schema_version is replay.request_version is None


@pytest.mark.integration
@pytest.mark.parametrize("legacy_sprint0", [False, True])
def test_fresh_database_and_sprint0_upgrade(
    isolated_postgres_url: str, legacy_sprint0: bool
) -> None:
    project_id = uuid4()
    if legacy_sprint0:
        migration = (
            Path(__file__).resolve().parents[1] / "app/migrations/0001_sprint0.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(isolated_postgres_url) as connection:
            connection.execute(migration)
            connection.execute(
                "CREATE TABLE schema_migrations (version text PRIMARY KEY, "
                "applied_at timestamptz NOT NULL DEFAULT now())"
            )
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES ('0001_sprint0.sql')"
            )
            connection.execute("INSERT INTO tenants (id) VALUES ('upgrade-test')")
            connection.execute(
                "INSERT INTO projects (id, tenant_id, title) "
                "VALUES (%s, 'upgrade-test', 'Existing Sprint 0 project')",
                (project_id,),
            )
    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    store.run_migrations()
    with psycopg.connect(isolated_postgres_url) as connection:
        migrations = connection.execute(
            "SELECT version, sha256 FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [row[0] for row in migrations] == [
            "0001_sprint0.sql", "0002_sprint1_foundation.sql", "0003_transcript_ingestion.sql", "0004_chat_and_retrieval.sql", "0005_ordered_playlists.sql", "0006_local_generation_usage.sql", "0007_embedding_spaces.sql", "0008_resumable_embeddings.sql", "0009_transcript_timeline.sql", "0010_asr_checkpoints.sql", "0011_media_lifecycle.sql", "0012_scoped_audio_cleanup.sql", "0013_visual_checkpoints.sql", "0014_video_lifecycle.sql", "0015_retained_visual_gallery.sql", "0016_retained_ocr_index.sql", "0017_video_workflows.sql", "0018_visual_selection_manifest.sql", "0019_local_frame_descriptions.sql", "0020_curriculum_contexts.sql", "0021_curriculum_drafts.sql", "0022_curriculum_runs.sql", "0023_curriculum_delivery.sql", "0024_curriculum_request_identity.sql"
        ]
        assert all(len(row[1]) == 64 for row in migrations)
        if legacy_sprint0:
            row = connection.execute(
                "SELECT title, status, created_at, updated_at, archived_at "
                "FROM projects WHERE tenant_id = 'upgrade-test' AND id = %s",
                (project_id,),
            ).fetchone()
            assert row[0] == "Existing Sprint 0 project"
            assert row[1] == "active"
            assert row[2] == row[3]
            assert row[4] is None
        connection.execute(
            "UPDATE schema_migrations SET sha256 = %s "
            "WHERE version = '0002_sprint1_foundation.sql'",
            ("0" * 64,),
        )
    with pytest.raises(RuntimeError, match="checksum changed"):
        store.run_migrations()


@pytest.mark.integration
@pytest.mark.anyio
async def test_postgres_api_auth_and_every_project_operation_are_tenant_scoped(
    isolated_postgres_url: str,
) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.config import Settings
    from app.main import create_app

    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    secret = "integration-trusted-proxy-secret"
    app = create_app(
        settings=Settings(
            environment="test",
            store_backend="postgres",
            auto_migrate=False,
            auth_mode="trusted_proxy",
            trusted_proxy_secret=secret,
        ),
        store=store,
    )
    tenant_a = {
        "X-Trusted-Proxy-Secret": secret,
        "X-Authenticated-Subject": "postgres-api-user-a",
        "X-Authenticated-Tenant": "postgres-api-tenant-a",
    }
    tenant_b = {
        **tenant_a,
        "X-Authenticated-Subject": "postgres-api-user-b",
        "X-Authenticated-Tenant": "postgres-api-tenant-b",
    }
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/api/v1/projects")).status_code == 401
        created = await client.post(
            "/api/v1/projects", headers=tenant_a, json={"title": "API isolation"}
        )
        assert created.status_code == 201
        path = f"/api/v1/projects/{created.json()['id']}"
        foreign_responses = [
            await client.get(path, headers=tenant_b),
            await client.patch(path, headers=tenant_b, json={"title": "Foreign rename"}),
            await client.post(path + "/archive", headers=tenant_b),
            await client.post(path + "/restore", headers=tenant_b),
            await client.delete(path, headers=tenant_b),
        ]
        assert all(response.status_code == 404 for response in foreign_responses)
        assert (await client.get("/api/v1/projects", headers=tenant_b)).json() == {"items": []}
        renamed = await client.patch(path, headers=tenant_a, json={"title": "Renamed"})
        assert renamed.status_code == 200
        archived = await client.post(path + "/archive", headers=tenant_a)
        assert archived.json()["status"] == "archived"
        assert (await client.get("/api/v1/projects", headers=tenant_a)).json() == {"items": []}
        restored = await client.post(path + "/restore", headers=tenant_a)
        assert restored.json()["status"] == "active"
        assert (await client.delete(path, headers=tenant_a)).status_code == 204
        assert (await client.get(path, headers=tenant_a)).status_code == 404


@pytest.mark.integration
@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_postgres_pgvector_cited_answer(isolated_postgres_url: str) -> None:
    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    service = TutorialService(
        store,
        DeterministicHashEmbeddingProvider(),
        EvidenceExtractiveAnswerProvider(),
    )
    suffix = uuid4().hex[:12]
    tenant_id = f"postgres-test-{suffix}"
    principal = AuthenticatedPrincipal(
        provider="integration-test",
        subject=f"user-{suffix}",
        tenant_id=tenant_id,
    )
    other_principal = AuthenticatedPrincipal(
        provider="integration-test",
        subject=f"other-{suffix}",
        tenant_id=f"other-{suffix}",
    )
    project = service.create_project(principal, ProjectCreate(title="Integration test"))
    try:
        assert service.list_projects(principal, ProjectListStatus.ACTIVE).items == [project]
        renamed = service.update_project(
            principal,
            project.id,
            ProjectUpdate(title="Renamed integration project"),
        )
        assert renamed.title == "Renamed integration project"
        archived = service.archive_project(principal, project.id)
        assert archived.status.value == "archived"
        assert service.list_projects(principal, ProjectListStatus.ACTIVE).items == []
        restored = service.restore_project(principal, project.id)
        assert restored.status.value == "active"

        with pytest.raises(LookupError):
            service.get_project(other_principal, project.id)

        ingested = service.ingest_transcript(
            principal,
            project.id,
            TranscriptIngestRequest(
                filename="integration.vtt",
                content=(
                    "WEBVTT\n\n"
                    "00:00:01.000 --> 00:00:04.000\n"
                    "The health endpoint reports service availability.\n"
                ),
                authorization_mode="owner_upload",
                idempotency_key=f"postgres-test-{project.id}",
            ),
        )
        response = service.ask(
            principal,
            project.id,
            "Which endpoint reports service health?",
        )
        assert response.abstained is False
        assert response.citations[0].source_id == ingested.source.id

        job_id = uuid4()
        attempt_id = uuid4()
        with psycopg.connect(isolated_postgres_url) as connection:
            connection.execute(
                """
                INSERT INTO processing_jobs (
                    id, tenant_id, project_id, source_id, job_type, stage,
                    status, idempotency_key
                ) VALUES (%s, %s, %s, %s, 'transcript', 'normalize',
                          'running', %s)
                """,
                (
                    job_id,
                    tenant_id,
                    project.id,
                    ingested.source.id,
                    f"job-{project.id}",
                ),
            )
            connection.execute(
                """
                INSERT INTO processing_attempts (
                    id, tenant_id, project_id, job_id, attempt_number, status
                ) VALUES (%s, %s, %s, %s, 1, 'running')
                """,
                (attempt_id, tenant_id, project.id, job_id),
            )

        service.delete_project(principal, project.id)
        with pytest.raises(LookupError):
            service.get_project(principal, project.id)

        with psycopg.connect(isolated_postgres_url) as connection:
            for table in (
                "sources",
                "content_segments",
                "retrieval_runs",
                "processing_jobs",
                "processing_attempts",
            ):
                count = connection.execute(
                    f"SELECT count(*) FROM {table} WHERE tenant_id = %s AND project_id = %s",
                    (tenant_id, project.id),
                ).fetchone()[0]
                assert count == 0, table
            delete_audits = connection.execute(
                """
                SELECT count(*) FROM audit_events
                WHERE tenant_id = %s AND project_id = %s
                  AND action = 'project.deleted'
                """,
                (tenant_id, project.id),
            ).fetchone()[0]
            assert delete_audits == 1
    finally:
        with psycopg.connect(isolated_postgres_url) as connection:
            connection.execute(
                "DELETE FROM projects WHERE tenant_id = %s AND id = %s",
                (tenant_id, project.id),
            )
            connection.execute(
                "DELETE FROM audit_events WHERE tenant_id IN (%s, %s)",
                (tenant_id, other_principal.tenant_id),
            )
            connection.execute(
                "DELETE FROM tenants WHERE id IN (%s, %s)",
                (tenant_id, other_principal.tenant_id),
            )
            identity_rows = connection.execute(
                """
                DELETE FROM auth_identities
                WHERE provider = 'integration-test'
                  AND subject IN (%s, %s)
                RETURNING user_id
                """,
                (principal.subject, other_principal.subject),
            ).fetchall()
            for row in identity_rows:
                connection.execute("DELETE FROM users WHERE id = %s", (row[0],))
