"""Save explicitly selected published evidence without model or artifact access."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..chat.contracts import EvidenceView
from ..postgres import PostgresStore
from ..provenance import checked_visual_origin
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .contracts import (
    MAX_EVIDENCE_CHARACTERS,
    MAX_EVIDENCE_SEGMENTS,
    GenerationRequest,
    SourceVersionPin,
    TutorialEvidenceSnapshot,
)
from .persistence import MAX_CONTEXT_BYTES, ContextCreate, ContextView


LOGGER = logging.getLogger("tutorial_workspace")


class ContextRepository:
    def __init__(self, store: PostgresStore):
        self.store = store

    @staticmethod
    def _scope(connection, tenant: str, project: UUID, actor: UUID, *, write: bool):
        member = connection.execute(
            "SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE",
            (tenant, actor),
        ).fetchone()
        if member is None:
            raise ProjectNotFoundError("project not found")
        lock = " FOR UPDATE" if write else " FOR SHARE"
        row = connection.execute(
            "SELECT status FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL" + lock,
            (tenant, project),
        ).fetchone()
        if row is None:
            raise ProjectNotFoundError("project not found")
        return row

    @staticmethod
    def _view(row) -> ContextView:
        # JSON parsing preserves strict UUID/datetime semantics on domain values.
        return ContextView.model_validate_json(json.dumps({
            "id": str(row["id"]), "tenant_id": row["tenant_id"],
            "project_id": str(row["project_id"]), "created_at": row["created_at"].isoformat(),
            "request": row["request"], "tutorial_snapshots": row["tutorial_snapshots"],
        }))

    @staticmethod
    def _body(body: ContextCreate) -> ContextCreate:
        try:
            if not isinstance(body, ContextCreate):
                raise ValueError()
            return ContextCreate.model_validate(body.model_dump(warnings=False))
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise SourceError("invalid_curriculum_context", "The curriculum context could not be validated.", 422) from None

    @staticmethod
    def _unavailable():
        return SourceError("curriculum_source_unavailable", "Choose a published source generation with matching evidence.", 409)

    @staticmethod
    def _overflow():
        return SourceError("curriculum_evidence_too_large", "The selected evidence exceeds the saved context limit.", 422)

    def _snapshots(self, connection, request: GenerationRequest) -> list[TutorialEvidenceSnapshot]:
        snapshots = []
        count, characters = 0, 0
        for pin in request.selected_sources:
            source = connection.execute(
                """SELECT filename,active_generation FROM sources
                   WHERE tenant_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL FOR KEY SHARE""",
                (request.tenant_id, request.project_id, pin.source_id),
            ).fetchone()
            if not source or source["active_generation"] is None or source["active_generation"] < pin.generation:
                raise self._unavailable()
            version = connection.execute(
                """SELECT processing_version FROM processing_versions
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s""",
                (request.tenant_id, request.project_id, pin.source_id, pin.generation),
            ).fetchone()
            if version and version["processing_version"] != pin.processing_version:
                raise self._unavailable()
            rows = connection.execute(
                """SELECT cs.*,s.filename AS source_filename,to_jsonb(ar) AS asr_origin,
                          vo.origin AS visual_origin
                   FROM content_segments cs
                   JOIN sources s ON s.tenant_id=cs.tenant_id AND s.project_id=cs.project_id AND s.id=cs.source_id
                   LEFT JOIN processing_versions v ON v.tenant_id=cs.tenant_id AND v.project_id=cs.project_id
                     AND v.source_id=cs.source_id AND v.generation=cs.generation
                   LEFT JOIN asr_runs ar ON ar.tenant_id=v.tenant_id AND ar.project_id=v.project_id
                     AND ar.source_id=v.source_id AND ar.job_id=v.asr_job_id AND ar.completed_at IS NOT NULL
                   LEFT JOIN visual_index_origins vo ON vo.tenant_id=cs.tenant_id AND vo.project_id=cs.project_id
                     AND vo.source_id=cs.source_id AND vo.generation=cs.generation
                   WHERE cs.tenant_id=%s AND cs.project_id=%s AND cs.source_id=%s AND cs.generation=%s
                   ORDER BY cs.start_ms,cs.end_ms,cs.id LIMIT %s""",
                (request.tenant_id, request.project_id, pin.source_id, pin.generation,
                 MAX_EVIDENCE_SEGMENTS - count + 1),
            ).fetchall()
            if not rows:
                raise self._unavailable()
            if count + len(rows) > MAX_EVIDENCE_SEGMENTS:
                raise self._overflow()
            segments = []
            for row in rows:
                if row["processing_version"] != pin.processing_version:
                    raise self._unavailable()
                characters += len(row["text"])
                if characters > MAX_EVIDENCE_CHARACTERS:
                    raise self._overflow()
                row["visual_origin"] = checked_visual_origin(row)
                try:
                    segment = EvidenceView(segment_id=row["id"], **{
                        key: row[key] for key in EvidenceView.model_fields if key != "segment_id"
                    })
                    # Validate every row before proceeding to subsequent sources.
                    TutorialEvidenceSnapshot(pin=pin, segments=[segment])
                except (ValidationError, ValueError, TypeError):
                    raise self._unavailable() from None
                segments.append(segment)
            snapshots.append(TutorialEvidenceSnapshot(pin=pin, segments=segments))
            count += len(segments)
        return snapshots

    def create(self, tenant: str, project: UUID, actor: UUID, body: ContextCreate) -> ContextView:
        body = self._body(body)
        try:
            request = GenerationRequest(
                tenant_id=tenant, project_id=project, learner=body.learner,
                selected_sources=[SourceVersionPin(tenant_id=tenant, project_id=project, **item.model_dump())
                                  for item in sorted(body.selected_sources, key=lambda item: str(item.source_id))],
            )
        except (ValidationError, ValueError, TypeError):
            raise SourceError("invalid_curriculum_context", "The curriculum context could not be validated.", 422) from None
        payload = request.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.store._connect() as connection:
            state = self._scope(connection, tenant, project, actor, write=True)
            existing = connection.execute(
                """SELECT * FROM curriculum_contexts
                   WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s""",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != digest:
                    raise SourceError("idempotency_conflict", "This context key was used for different input.", 409)
                return self._view(existing)
            if state["status"] != "active":
                raise SourceError("project_archived", "Restore the project before saving a new curriculum context.", 409)
            snapshots = self._snapshots(connection, request)
            snapshot_payload = [snapshot.model_dump(mode="json") for snapshot in snapshots]
            # Match PostgreSQL jsonb's spaced rendering so its CHECK cannot reject
            # an accepted compact payload solely because separators grow on disk.
            if len(json.dumps(snapshot_payload, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES:
                raise self._overflow()
            row = connection.execute(
                """INSERT INTO curriculum_contexts
                   (tenant_id,project_id,id,actor_user_id,idempotency_key,request_sha256,request,tutorial_snapshots)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, uuid4(), actor, body.idempotency_key, digest, Jsonb(payload), Jsonb(snapshot_payload)),
            ).fetchone()
            for pin in request.selected_sources:
                connection.execute(
                    """INSERT INTO curriculum_context_sources
                       (tenant_id,project_id,context_id,source_id,generation,processing_version)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (tenant, project, row["id"], pin.source_id, pin.generation, pin.processing_version),
                )
            result = self._view(row)
        LOGGER.info(json.dumps({"event": "curriculum_context_committed", "tenant_id": tenant,
                                "project_id": str(project), "context_id": str(result.id),
                                "source_count": len(snapshots),
                                "segment_count": sum(len(item.segments) for item in snapshots)}))
        return result

    def read(self, tenant: str, project: UUID, actor: UUID, context_id: UUID) -> ContextView:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor, write=False)
            row = connection.execute(
                "SELECT * FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (tenant, project, context_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum context not found")
            return self._view(row)

    def delete(self, tenant: str, project: UUID, actor: UUID, context_id: UUID) -> None:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor, write=True)
            row = connection.execute(
                "DELETE FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING id",
                (tenant, project, context_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum context not found")
        LOGGER.info(json.dumps({"event": "curriculum_context_deleted", "tenant_id": tenant,
                                "project_id": str(project), "context_id": str(context_id)}))
