"""Read published, version-pinned evidence without model or artifact access."""
from uuid import UUID

from pydantic import BaseModel

from ..chat.contracts import EvidenceView
from ..postgres import PostgresStore
from ..provenance import AsrOrigin
from ..store import ProjectNotFoundError
from .contracts import SourceError

PAGE_SIZE = 50
# Durable uploads cap at 10,000 chunks. The older validation endpoint retained
# one segment/cue under a 2-million-character body and can exceed that count.
# Browsing does not broaden ingestion: this only covers already retained evidence.
MAX_PAGES = 2_000


class TranscriptPage(BaseModel):
    source_id: UUID
    source_filename: str
    source_kind: str
    source_status: str
    generation: int | None
    active_generation: int | None
    processing_version: str | None
    page: int
    page_size: int = PAGE_SIZE
    total_segments: int
    total_pages: int
    items: list[EvidenceView]
    asr_origin: AsrOrigin | None = None


class TranscriptRepository:
    def __init__(self, store: PostgresStore):
        self.store = store

    def read(self, tenant: str, project: UUID, actor: UUID, source: UUID,
             *, generation: int | None = None, page: int = 1) -> TranscriptPage:
        if not 1 <= page <= MAX_PAGES or (generation is not None and not 1 <= generation <= 2_147_483_647):
            raise SourceError("validation_error", "Invalid transcript page or generation.", 422)
        if page > 1 and generation is None:
            raise SourceError("transcript_generation_required", "Choose a transcript generation before changing pages.", 422)
        with self.store._connect() as connection:
            # No project lock: each response sees one committed metadata/evidence
            # snapshot, while indexing/deletion can proceed in other transactions.
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            self.store._require_membership(connection, tenant, actor)
            row = connection.execute(
                """SELECT s.filename,s.kind,s.status,s.active_generation FROM sources s
                   JOIN projects p ON p.tenant_id=s.tenant_id AND p.id=s.project_id
                   WHERE s.tenant_id=%s AND s.project_id=%s AND s.id=%s
                     AND s.deleted_at IS NULL AND p.deleted_at IS NULL""",
                (tenant, project, source),
            ).fetchone()
            if not row:
                raise ProjectNotFoundError("source not found")
            selected = row["active_generation"] if generation is None else generation
            if generation is not None and (row["active_generation"] is None or generation > row["active_generation"]):
                raise ProjectNotFoundError("transcript generation not found")
            scope = (tenant, project, source, selected)
            summary = connection.execute(
                """SELECT count(*) AS total,min(processing_version) AS version FROM content_segments
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s
                     AND modality='transcript'""", scope,
            ).fetchone()
            total = summary["total"]
            pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            if (generation is not None and not total) or page > max(1, pages):
                raise ProjectNotFoundError("transcript page not found")
            segments = connection.execute(
                """SELECT id,source_id,start_ms,end_ms,text,modality,processing_version,generation
                   FROM content_segments
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s
                     AND modality='transcript'
                   ORDER BY start_ms,end_ms,id LIMIT %s OFFSET %s""",
                (*scope, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            ).fetchall()
            origin = connection.execute(
                '''SELECT to_jsonb(ar) AS origin FROM processing_versions v
                   JOIN asr_runs ar ON ar.tenant_id=v.tenant_id AND ar.project_id=v.project_id
                     AND ar.source_id=v.source_id AND ar.job_id=v.asr_job_id AND ar.completed_at IS NOT NULL
                   WHERE v.tenant_id=%s AND v.project_id=%s AND v.source_id=%s AND v.generation=%s''', scope,
            ).fetchone()
            asr_origin = AsrOrigin.model_validate(origin['origin']) if origin else None
            return TranscriptPage(
                source_id=source, source_filename=row["filename"], source_kind=row["kind"],
                source_status=row["status"], generation=selected, active_generation=row["active_generation"],
                processing_version=summary["version"], page=page, total_segments=total, total_pages=pages,
                asr_origin=asr_origin,
                items=[EvidenceView(segment_id=item["id"], source_filename=row["filename"], asr_origin=asr_origin,
                                    **{key: item[key] for key in EvidenceView.model_fields
                                       if key not in {"segment_id", "source_filename", "asr_origin", "frame_id", "visual_origin"}}) for item in segments],
            )
