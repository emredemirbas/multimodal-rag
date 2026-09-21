from __future__ import annotations

from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .models import (
    EvidenceSegment,
    Project,
    RetrievalHit,
    RetrievalRun,
    Source,
)
from .store import ProjectNotFoundError


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{value:.10f}" for value in vector) + "]"

    @staticmethod
    def _parse_vector(value: object) -> list[float]:
        if isinstance(value, str):
            return [float(item) for item in value.strip("[]").split(",") if item]
        return [float(item) for item in value]  # type: ignore[arg-type]

    def run_migrations(self) -> None:
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(migrations_dir.glob("*.sql")):
                if migration.name in applied:
                    continue
                connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (migration.name,),
                )

    def healthcheck(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def create_project(self, project: Project) -> Project:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tenants (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (project.tenant_id,),
            )
            connection.execute(
                """
                INSERT INTO projects (id, tenant_id, title, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (project.id, project.tenant_id, project.title, project.created_at),
            )
        return project

    def get_project(self, tenant_id: str, project_id: UUID) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, tenant_id, title, created_at
                FROM projects
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                """,
                (tenant_id, project_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError("project not found")
        return Project.model_validate(row)

    def get_source_by_idempotency_key(
        self, tenant_id: str, project_id: UUID, idempotency_key: str
    ) -> Source | None:
        self.get_project(tenant_id, project_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, tenant_id, project_id, filename, authorization_mode,
                       status, processing_version, segment_count, frame_count, created_at
                FROM sources
                WHERE tenant_id = %s AND project_id = %s AND idempotency_key = %s
                """,
                (tenant_id, project_id, idempotency_key),
            ).fetchone()
        return Source.model_validate(row) if row else None

    def save_source(
        self, source: Source, segments: list[EvidenceSegment], idempotency_key: str
    ) -> Source:
        self.get_project(source.tenant_id, source.project_id)
        saved = source.model_copy(update={"segment_count": len(segments)})
        with self._connect() as connection:
            lock_key = f"{saved.tenant_id}:{saved.project_id}:{idempotency_key}"
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (lock_key,),
            )
            existing = connection.execute(
                """
                SELECT id, tenant_id, project_id, filename, authorization_mode,
                       status, processing_version, segment_count, frame_count, created_at
                FROM sources
                WHERE tenant_id = %s AND project_id = %s AND idempotency_key = %s
                FOR UPDATE
                """,
                (saved.tenant_id, saved.project_id, idempotency_key),
            ).fetchone()
            if existing:
                return Source.model_validate(existing)

            connection.execute(
                """
                INSERT INTO sources (
                    id, tenant_id, project_id, filename, authorization_mode,
                    status, processing_version, segment_count, frame_count,
                    idempotency_key, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    saved.id,
                    saved.tenant_id,
                    saved.project_id,
                    saved.filename,
                    saved.authorization_mode.value,
                    saved.status,
                    saved.processing_version,
                    saved.segment_count,
                    saved.frame_count,
                    idempotency_key,
                    saved.created_at,
                ),
            )
            for segment in segments:
                connection.execute(
                    """
                    INSERT INTO content_segments (
                        id, tenant_id, project_id, source_id, modality,
                        start_ms, end_ms, text, embedding, processing_version, frame_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                    """,
                    (
                        segment.id,
                        segment.tenant_id,
                        segment.project_id,
                        segment.source_id,
                        segment.modality,
                        segment.start_ms,
                        segment.end_ms,
                        segment.text,
                        self._vector_literal(segment.embedding),
                        segment.processing_version,
                        segment.frame_id,
                    ),
                )
        return saved

    def get_source(self, tenant_id: str, project_id: UUID, source_id: UUID) -> Source:
        self.get_project(tenant_id, project_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, tenant_id, project_id, filename, authorization_mode,
                       status, processing_version, segment_count, frame_count, created_at
                FROM sources
                WHERE tenant_id = %s AND project_id = %s AND id = %s
                """,
                (tenant_id, project_id, source_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError("source not found")
        return Source.model_validate(row)

    def search(
        self,
        tenant_id: str,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievalHit]:
        self.get_project(tenant_id, project_id)
        vector = self._vector_literal(query_embedding)
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT cs.*, s.filename,
                           websearch_to_tsquery('simple', %s) AS query,
                           GREATEST(0.0, 1.0 - (cs.embedding <=> %s::vector)) AS semantic
                    FROM content_segments cs
                    JOIN sources s
                      ON s.tenant_id = cs.tenant_id
                     AND s.project_id = cs.project_id
                     AND s.id = cs.source_id
                    WHERE cs.tenant_id = %s AND cs.project_id = %s
                )
                SELECT *,
                       (
                         CASE WHEN search_document @@ query THEN 0.55 ELSE 0.0 END
                         + 0.15 * ts_rank_cd(search_document, query)
                         + 0.45 * semantic
                       ) AS score
                FROM candidates
                ORDER BY score DESC, start_ms ASC
                LIMIT %s
                """,
                (query_text, vector, tenant_id, project_id, limit),
            ).fetchall()

        hits: list[RetrievalHit] = []
        for row in rows:
            segment = EvidenceSegment(
                id=row["id"],
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                source_id=row["source_id"],
                modality=row["modality"],
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                text=row["text"],
                embedding=self._parse_vector(row["embedding"]),
                processing_version=row["processing_version"],
                frame_id=row["frame_id"],
            )
            hits.append(
                RetrievalHit(
                    segment=segment,
                    source_filename=row["filename"],
                    score=float(row["score"]),
                )
            )
        return hits

    def save_retrieval_run(self, run: RetrievalRun) -> None:
        self.get_project(run.tenant_id, run.project_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_runs (
                    id, tenant_id, project_id,
                    embedding_provider, embedding_model,
                    answer_provider, answer_model,
                    query_sha256, retrieved_segment_ids, cited_segment_ids,
                    candidate_count, latency_ms, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    run.id,
                    run.tenant_id,
                    run.project_id,
                    run.embedding_provider,
                    run.embedding_model,
                    run.answer_provider,
                    run.answer_model,
                    run.query_sha256,
                    run.retrieved_segment_ids,
                    run.cited_segment_ids,
                    run.candidate_count,
                    run.latency_ms,
                    run.created_at,
                ),
            )
