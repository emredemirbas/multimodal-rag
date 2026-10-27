"""Public selected-frame inspection: no storage key, original digest or raw run."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from ..provenance import VisualOrigin


class RetainedFrame(BaseModel):
    id: UUID
    ordinal: int = Field(ge=0, le=19)
    timestamp_ms: int = Field(ge=0, le=599999)
    sample_target_ms: int = Field(ge=0, le=599999)
    width: int = Field(ge=1, le=960)
    height: int = Field(ge=1, le=540)
    ocr_text: str = Field(max_length=16000)


class VisualGallery(BaseModel):
    source_id: UUID
    source_filename: str
    generation: int | None = None
    processing_version: str | None = None
    published_at: datetime | None = None
    origin: VisualOrigin | None = None
    searchable: bool = False
    active_index_generation: int | None = None
    active_embedding_space: str | None = None
    items: list[RetainedFrame] = Field(default_factory=list, max_length=20)
