from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row

from .models import (
    AuthenticatedPrincipal,
    EvidenceSegment,
    Project,
    ProjectListStatus,
    RetrievalHit,
    RetrievalRun,
    Source,
)
from .store import ProjectNotFoundError


class DatabaseUnavailableError(RuntimeError):
    """A connection failure that is safe to expose without a connection string."""


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.database_url, row_factory=dict_row)
        except psycopg.Error:
            raise DatabaseUnavailableError("database connection failed") from None

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
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("multimodal-tutorial-workspace:migrations",),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    sha256 text,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            connection.execute(
                "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS sha256 text"
            )
            applied = {
                row["version"]: row["sha256"]
                for row in connection.execute(
                    "SELECT version, sha256 FROM schema_migrations"
                )
            }
            for migration in sorted(migrations_dir.glob("*.sql")):
                script = migration.read_text(encoding="utf-8")
                checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()
                stored_checksum = applied.get(migration.name)
                if stored_checksum:
                    if stored_checksum != checksum:
                        raise RuntimeError(
                            f"applied migration checksum changed: {migration.name}"
                        )
                    continue
                if migration.name in applied:
                    connection.execute(
                        "UPDATE schema_migrations SET sha256 = %s WHERE version = %s",
                        (checksum, migration.name),
                    )
                    continue
                connection.execute(script)
                connection.execute(
                    "INSERT INTO schema_migrations (version, sha256) VALUES (%s, %s)",
                    (migration.name, checksum),
                )

    def healthcheck(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def bootstrap_principal(self, principal: AuthenticatedPrincipal) -> UUID:
        proposed_user_id = uuid5(
            NAMESPACE_URL,
            f"identity:{principal.provider}:{principal.subject}",
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tenants (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (principal.tenant_id,),
            )
            connection.execute(
                "INSERT INTO users (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (proposed_user_id,),
            )
            identity = connection.execute(
                """
                INSERT INTO auth_identities (provider, subject, user_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (provider, subject) DO UPDATE
                    SET subject = EXCLUDED.subject
                RETURNING user_id
                """,
                (principal.provider, principal.subject, proposed_user_id),
            ).fetchone()
            user_id = identity["user_id"]
            connection.execute(
                """
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (%s, %s, 'owner')
                ON CONFLICT (tenant_id, user_id) DO NOTHING
                """,
                (principal.tenant_id, user_id),
            )
        return user_id

    @staticmethod
    def _project_from_row(row: dict[str, object]) -> Project:
        return Project.model_validate(row)

    @staticmethod
    def _record_audit(
        connection: psycopg.Connection,
        *,
        tenant_id: str,
        project_id: UUID,
        actor_user_id: UUID,
        action: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                id, tenant_id, project_id, actor_user_id, action, details
            ) VALUES (%s, %s, %s, %s, %s, '{}'::jsonb)
            """,
            (uuid4(), tenant_id, project_id, actor_user_id, action),
        )

    @staticmethod
    def _require_membership(
        connection: psycopg.Connection, tenant_id: str, actor_user_id: UUID
    ) -> None:
        membership = connection.execute(
            """
            SELECT 1
            FROM memberships
            WHERE tenant_id = %s AND user_id = %s
            """,
            (tenant_id, actor_user_id),
        ).fetchone()
        if membership is None:
            raise ProjectNotFoundError("project not found")

    def create_project(self, project: Project, actor_user_id: UUID) -> Project:
        with self._connect() as connection:
            self._require_membership(connection, project.tenant_id, actor_user_id)
            connection.execute(
                """
                INSERT INTO projects (
                    id, tenant_id, title, status, created_at, updated_at, archived_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    project.id,
                    project.tenant_id,
                    project.title,
                    project.status.value,
                    project.created_at,
                    project.updated_at,
                    project.archived_at,
                ),
            )
            self._record_audit(
                connection,
                tenant_id=project.tenant_id,
                project_id=project.id,
                actor_user_id=actor_user_id,
                action="project.created",
            )
        return project

    def list_projects(
        self, tenant_id: str, status: ProjectListStatus
    ) -> list[Project]:
        status_filter = "" if status == ProjectListStatus.ALL else "AND status = %s"
        parameters: tuple[object, ...]
        if status == ProjectListStatus.ALL:
            parameters = (tenant_id,)
        else:
            parameters = (tenant_id, status.value)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, tenant_id, title, status, created_at, updated_at, archived_at
                FROM projects
                WHERE tenant_id = %s AND deleted_at IS NULL {status_filter}
                ORDER BY updated_at DESC, id DESC
                """,
                parameters,
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def get_project(self, tenant_id: str, project_id: UUID) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, tenant_id, title, status, created_at, updated_at, archived_at
                FROM projects
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                """,
                (tenant_id, project_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError("project not found")
        return self._project_from_row(row)

    def update_project_title(
        self,
        tenant_id: str,
        project_id: UUID,
        title: str,
        actor_user_id: UUID,
    ) -> Project:
        with self._connect() as connection:
            self._require_membership(connection, tenant_id, actor_user_id)
            row = connection.execute(
                """
                UPDATE projects
                SET title = %s, updated_at = now()
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                RETURNING id, tenant_id, title, status,
                          created_at, updated_at, archived_at
                """,
                (title, tenant_id, project_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("project not found")
            self._record_audit(
                connection,
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.renamed",
            )
        return self._project_from_row(row)

    def archive_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project:
        with self._connect() as connection:
            self._require_membership(connection, tenant_id, actor_user_id)
            row = connection.execute(
                """
                UPDATE projects
                SET status = 'archived', archived_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                  AND status = 'active'
                RETURNING id, tenant_id, title, status,
                          created_at, updated_at, archived_at
                """,
                (tenant_id, project_id),
            ).fetchone()
            if row is not None:
                self._record_audit(
                    connection,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    actor_user_id=actor_user_id,
                    action="project.archived",
                )
            else:
                row = connection.execute(
                    """
                    SELECT id, tenant_id, title, status,
                           created_at, updated_at, archived_at
                    FROM projects
                    WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                    """,
                    (tenant_id, project_id),
                ).fetchone()
                if row is None:
                    raise ProjectNotFoundError("project not found")
        return self._project_from_row(row)

    def restore_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project:
        with self._connect() as connection:
            self._require_membership(connection, tenant_id, actor_user_id)
            row = connection.execute(
                """
                UPDATE projects
                SET status = 'active', archived_at = NULL, updated_at = now()
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                  AND status = 'archived'
                RETURNING id, tenant_id, title, status,
                          created_at, updated_at, archived_at
                """,
                (tenant_id, project_id),
            ).fetchone()
            if row is not None:
                self._record_audit(
                    connection,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    actor_user_id=actor_user_id,
                    action="project.restored",
                )
            else:
                row = connection.execute(
                    """
                    SELECT id, tenant_id, title, status,
                           created_at, updated_at, archived_at
                    FROM projects
                    WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                    """,
                    (tenant_id, project_id),
                ).fetchone()
                if row is None:
                    raise ProjectNotFoundError("project not found")
        return self._project_from_row(row)

    def delete_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> UUID:
        cleanup_id = uuid4()
        with self._connect() as connection:
            self._require_membership(connection, tenant_id, actor_user_id)
            project = connection.execute(
                "SELECT id FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL FOR UPDATE",
                (tenant_id, project_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError("project not found")
            connection.execute(
                "INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix) VALUES (%s,%s,%s,%s,%s)",
                (cleanup_id, tenant_id, project_id, actor_user_id, f"{tenant_id}/{project_id}/"),
            )
            deleted = connection.execute(
                """
                DELETE FROM projects
                WHERE tenant_id = %s AND id = %s AND deleted_at IS NULL
                RETURNING id
                """,
                (tenant_id, project_id),
            ).fetchone()
            if deleted is None:
                raise ProjectNotFoundError("project not found")
            self._record_audit(
                connection,
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.deleted",
            )
        return cleanup_id

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
                    idempotency_key, created_at, active_generation
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
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
        source_ids: list[UUID] | None = None,
    ) -> list[RetrievalHit]:
        from .providers import content_tokens
        from .retrieval import CANDIDATES_PER_CHANNEL, fuse_and_rerank
        self.get_project(tenant_id, project_id)
        for source_id in source_ids or []:
            self.get_source(tenant_id, project_id, source_id)
        vector = self._vector_literal(query_embedding)
        lexical_query = " | ".join(sorted(content_tokens(query_text))[:40])
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH candidates AS MATERIALIZED (
                    SELECT cs.*, s.filename,
                           to_tsquery('simple', %s) AS query,
                           GREATEST(0.0, 1.0 - (cs.embedding <=> %s::vector)) AS semantic
                    FROM content_segments cs
                    JOIN sources s
                      ON s.tenant_id = cs.tenant_id
                     AND s.project_id = cs.project_id
                     AND s.id = cs.source_id
                    WHERE cs.tenant_id = %s AND cs.project_id = %s
                      AND s.deleted_at IS NULL
                      AND s.active_generation IS NOT NULL
                      AND cs.generation = s.active_generation
                      AND (%s::uuid[] IS NULL OR cs.source_id = ANY(%s::uuid[]))
                ), lexical AS (
                    SELECT id, ts_rank_cd(search_document, query) AS score, 'lexical' AS channel
                    FROM candidates WHERE search_document @@ query
                    ORDER BY score DESC, id LIMIT %s
                ), semantic AS (
                    SELECT id, semantic AS score, 'semantic' AS channel FROM candidates
                    ORDER BY semantic DESC, id LIMIT %s
                ), ranks AS (
                    SELECT * FROM lexical UNION ALL SELECT * FROM semantic
                )
                SELECT c.*, r.score, r.channel FROM ranks r JOIN candidates c ON c.id=r.id
                ORDER BY r.channel, r.score DESC, c.id
                """,
                (lexical_query, vector, tenant_id, project_id, source_ids or None, source_ids or None,
                 CANDIDATES_PER_CHANNEL, CANDIDATES_PER_CHANNEL),
            ).fetchall()

        channels: dict[str, list[RetrievalHit]] = {"lexical": [], "semantic": []}
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
                generation=row["generation"],
                frame_id=row["frame_id"],
            )
            channels[row["channel"]].append(
                RetrievalHit(
                    segment=segment,
                    source_filename=row["filename"],
                    score=float(row["score"]),
                )
            )
        return fuse_and_rerank(query_text, list(channels.values()), limit)

    def save_retrieval_run(self, run: RetrievalRun) -> None:
        self.get_project(run.tenant_id, run.project_id)
        with self._connect() as connection:
            self.insert_retrieval_run(connection, run)

    @staticmethod
    def insert_retrieval_run(connection, run: RetrievalRun) -> None:
        connection.execute(
            """INSERT INTO retrieval_runs (
                id, tenant_id, project_id, embedding_provider, embedding_model,
                answer_provider, answer_model, query_sha256, retrieved_segment_ids,
                cited_segment_ids, candidate_count, latency_ms, created_at,
                retrieval_version, reranker_version, prompt_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run.id, run.tenant_id, run.project_id, run.embedding_provider, run.embedding_model,
             run.answer_provider, run.answer_model, run.query_sha256, run.retrieved_segment_ids,
             run.cited_segment_ids, run.candidate_count, run.latency_ms, run.created_at,
             run.retrieval_version, run.reranker_version, run.prompt_version),
        )
