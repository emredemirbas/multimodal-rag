from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
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
            "0001_sprint0.sql", "0002_sprint1_foundation.sql", "0003_transcript_ingestion.sql", "0004_chat_and_retrieval.sql", "0005_ordered_playlists.sql", "0006_local_generation_usage.sql", "0007_embedding_spaces.sql", "0008_resumable_embeddings.sql", "0009_transcript_timeline.sql", "0010_asr_checkpoints.sql", "0011_media_lifecycle.sql", "0012_scoped_audio_cleanup.sql", "0013_visual_checkpoints.sql"
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
