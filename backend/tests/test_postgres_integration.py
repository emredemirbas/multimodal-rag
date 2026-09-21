from __future__ import annotations

import os

import psycopg
from psycopg.conninfo import make_conninfo
import pytest

from app.models import ProjectCreate, TranscriptIngestRequest
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


@pytest.mark.integration
@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_postgres_pgvector_cited_answer() -> None:
    assert DATABASE_URL is not None
    store = PostgresStore(DATABASE_URL)
    store.run_migrations()
    service = TutorialService(
        store,
        DeterministicHashEmbeddingProvider(),
        EvidenceExtractiveAnswerProvider(),
    )
    project = service.create_project("postgres-test", ProjectCreate(title="Integration test"))
    try:
        ingested = service.ingest_transcript(
            "postgres-test",
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
            "postgres-test",
            project.id,
            "Which endpoint reports service health?",
        )
        assert response.abstained is False
        assert response.citations[0].source_id == ingested.source.id
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM projects WHERE tenant_id = %s AND id = %s",
                ("postgres-test", project.id),
            )
