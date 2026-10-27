from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ..models import QuestionRequest, QuestionResponse, ProjectCreate
from ..provenance import AsrOrigin, VisualOrigin


class ConversationCreate(ProjectCreate):
    title: str = Field(default="Tutorial questions", min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class MessageRequest(QuestionRequest):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("source_ids")
    @classmethod
    def normalize_sources(cls, values: list[UUID]) -> list[UUID]:
        return sorted(set(values), key=str)


class Conversation(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    created_at: datetime


class ConversationList(BaseModel):
    items: list[Conversation]


class ChatTurn(BaseModel):
    id: UUID
    sequence: int
    question: str
    source_ids: list[UUID]
    response: QuestionResponse
    created_at: datetime


class History(BaseModel):
    conversation: Conversation
    turns: list[ChatTurn]


class EvidenceView(BaseModel):
    segment_id: UUID
    source_id: UUID
    source_filename: str
    start_ms: int
    end_ms: int
    text: str
    modality: str
    processing_version: str
    generation: int
    asr_origin: AsrOrigin | None = None
    frame_id: UUID | None = None
    visual_origin: VisualOrigin | None = None
