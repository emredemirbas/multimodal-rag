"""Public provenance projections, never raw inference output or storage keys."""
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AsrOrigin(BaseModel):
    machine_generated: Literal[True] = True
    job_id: UUID
    generation: int = Field(ge=1)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    revision: str = Field(min_length=1, max_length=128)
    profile: str = Field(min_length=1, max_length=200)
    engine: str = Field(min_length=1, max_length=128)
    requested_language: Literal['auto', 'en', 'tr']
    assembly_version: str = Field(min_length=1, max_length=120)
    completed_at: datetime


class VisualOrigin(BaseModel):
    machine_generated: Literal[True] = True
    human_reviewed: Literal[False] = False
    job_id: UUID
    generation: int = Field(ge=1)
    profile: str = Field(pattern=r'^local-visual-v1:[a-f0-9]{64}$')
    language: Literal['en', 'tr', 'en+tr']
    engines: dict[str, str]
    checkpoint_version: str
    prepared_at: datetime


def checked_visual_origin(row):
    """Fail closed when managed frame evidence loses its versioned provenance."""
    origin = row.get('visual_origin')
    managed = row.get('visual_publication_job_id') is not None
    if not managed and origin is None:
        return None  # Legacy validation-only frames have no retained-image promise.
    try:
        parsed = VisualOrigin.model_validate(origin)
        if (not managed or row['modality'] != 'frame' or row['frame_id'] is None
                or row['start_ms'] != row['end_ms'] or parsed.generation >= row['generation']
                or row['processing_version'] != f"visual-ocr-chunks-v1:g{row['generation']}"):
            raise ValueError()
        return parsed
    except (ValueError, KeyError):
        from .sources.contracts import SourceError
        raise SourceError('invalid_visual_provenance', 'The visual evidence provenance could not be verified.', 503) from None


class AudioRetention(BaseModel):
    status: Literal['temporary', 'expired', 'cleanup_pending', 'cleanup_failed', 'deleted']
    processing_expires_at: datetime
    cleanup_id: UUID | None
    deleted_at: datetime | None

    @model_validator(mode='after')
    def consistent_state(self) -> Self:
        retired = self.status in {'cleanup_pending', 'cleanup_failed', 'deleted'}
        if retired != (self.cleanup_id is not None) or (self.status == 'deleted') != (self.deleted_at is not None):
            raise ValueError('Inconsistent original-audio retention state')
        return self
