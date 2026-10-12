from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from ..models import AuthorizationMode, Source


class SourceError(Exception):
    def __init__(self, code: str, detail: str, status: int = 422, *, transient: bool = False):
        self.code, self.detail, self.status, self.transient = code, detail, status, transient
        super().__init__(detail)


class Job(BaseModel):
    id: UUID
    source_id: UUID
    generation: int
    stage: str
    status: Literal['pending', 'running', 'retrying', 'succeeded', 'failed', 'cancelled']
    progress_percent: int
    attempt_count: int
    max_attempts: int
    failure_code: str | None = None
    failure_detail: str | None = None
    created_at: datetime
    updated_at: datetime


class ManagedSource(Source):
    kind: str = 'transcript'
    provider: str = 'upload'
    generation: int = 1
    active_generation: int | None = None
    retention_class: str = 'derived_only'
    failure_code: str | None = None
    failure_detail: str | None = None
    job: Job | None = None
    metadata: dict = Field(default_factory=dict)
    parent_playlist_source_id: UUID | None = None
    playlist_snapshot_generation: int | None = None
    active_embedding_space: str | None = None
    reindex_required: bool = False


class PlaylistMetadataItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=512, pattern=r'^[a-zA-Z0-9_+=./-]+$')
    video_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{11}$')
    title: str = Field(min_length=1, max_length=255)
    position: int = Field(strict=True, ge=0, le=1_000_000)


class PlaylistItem(BaseModel):
    id: UUID
    playlist_source_id: UUID
    generation: int
    position: int
    video_id: str
    title: str
    transcript_source_id: UUID | None = None


class SourceList(BaseModel):
    items: list[ManagedSource]
    playlist_items: list[PlaylistItem] = Field(default_factory=list)


class Registration(BaseModel):
    source: ManagedSource
    job: Job
    deduplicated: bool = False


class SourceCommand(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r'^[a-zA-Z0-9_-]+$')


class MetadataRegistration(SourceCommand):
    url: str = Field(min_length=1, max_length=2048)
    authorization_mode: AuthorizationMode


class Cleanup(BaseModel):
    id: UUID
    project_id: UUID
    status: Literal['pending', 'running', 'completed', 'failed']
    attempt_count: int
    failure_code: str | None = None
    completed_at: datetime | None = None
