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
