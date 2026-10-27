"""User-asserted temporal inspection; never verifies audiovisual identity."""
import json
import logging
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from ..provenance import AsrOrigin
from ..store import ProjectNotFoundError
from ..vision.gallery import VisualGalleryRepository
from ..vision.gallery_contracts import VisualGallery
from .contracts import SourceError

MAX_MATCHES = 5
MAX_EXCERPT = 4000
MAX_OFFSET = 600_000
LOGGER = logging.getLogger('tutorial_workspace')


class TranscriptIdentity(BaseModel):
    source_id: UUID
    source_filename: str
    generation: int
    active_generation: int
    processing_version: str
    asr_origin: AsrOrigin | None = None


class AlignedSpan(BaseModel):
    segment_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    excerpt: str = Field(max_length=MAX_EXCERPT)
    text_truncated: bool


class FrameAlignment(BaseModel):
    frame_id: UUID
    transcript_time_ms: int
    matches: list[AlignedSpan] = Field(max_length=MAX_MATCHES)
    matches_truncated: bool


class TimelineAlignment(BaseModel):
    method: Literal['retained-pts-in-transcript-spans-v1'] = 'retained-pts-in-transcript-spans-v1'
    relationship: Literal['user_asserted'] = 'user_asserted'
    semantics_verified: Literal[False] = False
    offset_ms: int = Field(ge=-MAX_OFFSET, le=MAX_OFFSET)
    gallery: VisualGallery
    transcript: TranscriptIdentity
    matched_frames: int = Field(ge=0, le=20)
    items: list[FrameAlignment] = Field(max_length=20)


class AlignmentRepository:
    def __init__(self, repository):
        self.repository = repository

    def read(self, tenant, project, actor, visual_source, transcript_source, *, assert_same_recording,
             offset_ms=0, visual_generation=None, transcript_generation=None):
        if (assert_same_recording is not True or type(offset_ms) is not int
                or not -MAX_OFFSET <= offset_ms <= MAX_OFFSET
                or (visual_generation is None) != (transcript_generation is None)
                or any(value is not None and (type(value) is not int or not 1 <= value <= 2_147_483_647)
                       for value in (visual_generation, transcript_generation))):
            raise SourceError('invalid_alignment', 'Confirm the same recording and use valid generations/offset.', 422)
        repo = self.repository
        with repo.store._connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            gallery = VisualGalleryRepository(repo).read_snapshot(connection, tenant, project, visual_source,
                                                                  actor, generation=visual_generation)
            # The gallery read also checks membership and nondeleted project scope.
            row = connection.execute(
                '''SELECT filename,kind,active_generation FROM sources
                   WHERE tenant_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL''',
                (tenant, project, transcript_source),
            ).fetchone()
            if row is None or row['kind'] not in {'transcript', 'audio'}:
                raise ProjectNotFoundError('transcript source not found')
            generation = row['active_generation'] if transcript_generation is None else transcript_generation
            if generation is not None and (row['active_generation'] is None or generation > row['active_generation']):
                raise ProjectNotFoundError('transcript generation not found')
            scope = (tenant, project, transcript_source, generation)
            versions = connection.execute(
                '''SELECT min(processing_version) AS first,max(processing_version) AS last FROM content_segments
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s AND modality='transcript' ''',
                scope,
            ).fetchone()
            if not versions['first']:
                if transcript_generation is not None: raise ProjectNotFoundError('transcript generation not found')
                raise SourceError('alignment_not_ready', 'Both a complete gallery and a published transcript are required.', 409)
            if versions['first'] != versions['last']:
                raise SourceError('artifact_integrity', 'The transcript processing identity could not be verified.', 409)
            if gallery.origin is None:
                raise SourceError('alignment_not_ready', 'Both a complete gallery and a published transcript are required.', 409)
            origin = connection.execute(
                '''SELECT to_jsonb(ar) AS origin FROM processing_versions v
                   JOIN asr_runs ar ON ar.tenant_id=v.tenant_id AND ar.project_id=v.project_id
                     AND ar.source_id=v.source_id AND ar.job_id=v.asr_job_id AND ar.completed_at IS NOT NULL
                   WHERE v.tenant_id=%s AND v.project_id=%s AND v.source_id=%s AND v.generation=%s''', scope,
            ).fetchone()
            transcript = TranscriptIdentity(source_id=transcript_source, source_filename=row['filename'],
                generation=generation, active_generation=row['active_generation'], processing_version=versions['first'],
                asr_origin=AsrOrigin.model_validate(origin['origin']) if origin else None)
            items = []
            for frame in gallery.items:
                point = frame.timestamp_ms + offset_ms
                # Only published content, half-open spans, no nearest-cue fallback.
                # Fetch one extra match for a truthful truncation flag; clip text in SQL.
                matches = connection.execute(
                    '''SELECT id AS segment_id,start_ms,end_ms,left(text,%s) AS excerpt,
                              length(text)>%s AS text_truncated FROM content_segments
                       WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s
                         AND modality='transcript' AND start_ms<=%s AND end_ms>%s
                       ORDER BY start_ms,end_ms,id LIMIT %s''',
                    (MAX_EXCERPT, MAX_EXCERPT, *scope, point, point, MAX_MATCHES + 1),
                ).fetchall()
                items.append(FrameAlignment(frame_id=frame.id, transcript_time_ms=point,
                    matches=[AlignedSpan.model_validate(match) for match in matches[:MAX_MATCHES]],
                    matches_truncated=len(matches) > MAX_MATCHES))
            result = TimelineAlignment(offset_ms=offset_ms, gallery=gallery, transcript=transcript,
                matched_frames=sum(bool(item.matches) for item in items), items=items)
        LOGGER.info(json.dumps({'event': 'timeline_alignment_read', 'tenant_id': tenant, 'project_id': str(project),
            'frames': len(items), 'matched_frames': result.matched_frames, 'relationship': 'user_asserted'}))
        return result
