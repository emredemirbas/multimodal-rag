from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


TenantId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]


class AuthorizationMode(str, Enum):
    OWNER_UPLOAD = "owner_upload"
    AUTHORIZED_UPLOAD = "authorized_upload"
    LICENSED_CONTENT = "licensed_content"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title cannot be blank")
        return stripped


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    tenant_id: TenantId
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FrameCandidate(BaseModel):
    timestamp_seconds: float = Field(ge=0)
    ocr_text: str = Field(default="", max_length=10_000)
    description: str = Field(default="", max_length=10_000)
    object_key: str | None = Field(default=None, max_length=512)


class TranscriptIngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2_000_000)
    authorization_mode: AuthorizationMode
    idempotency_key: str = Field(min_length=8, max_length=128)
    frame_candidates: list[FrameCandidate] = Field(default_factory=list, max_length=500)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        safe_name = value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if not safe_name.lower().endswith((".vtt", ".srt")):
            raise ValueError("only .vtt and .srt transcript files are supported")
        return safe_name


class TranscriptCue(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)


class EvidenceSegment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: TenantId
    project_id: UUID
    source_id: UUID
    modality: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str
    embedding: list[float]
    processing_version: str = "sprint0-v1"
    frame_id: UUID | None = None


class Source(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: TenantId
    project_id: UUID
    filename: str
    authorization_mode: AuthorizationMode
    status: str = "ready"
    processing_version: str = "sprint0-v1"
    segment_count: int = 0
    frame_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceIngested(BaseModel):
    source: Source
    deduplicated: bool = False


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("question must contain at least two characters")
        return stripped


class Citation(BaseModel):
    segment_id: UUID
    source_id: UUID
    source_filename: str
    start_ms: int
    end_ms: int
    modality: str
    frame_id: UUID | None = None
    score: float


class QuestionResponse(BaseModel):
    answer: str
    abstained: bool
    citations: list[Citation]
    retrieval_run_id: UUID
    provider: str
    model: str
    processing_version: str
    latency_ms: int


class RetrievalHit(BaseModel):
    segment: EvidenceSegment
    source_filename: str
    score: float


class RetrievalRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: TenantId
    project_id: UUID
    embedding_provider: str
    embedding_model: str
    answer_provider: str
    answer_model: str
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_segment_ids: list[UUID]
    cited_segment_ids: list[UUID]
    candidate_count: int
    latency_ms: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
