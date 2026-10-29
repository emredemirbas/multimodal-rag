"""HTTP input and saved, immutable tutorial-context projections."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .contracts import GenerationRequest, LearnerPreferences, TutorialEvidenceSnapshot


MAX_CONTEXT_BYTES = 4_000_000
StrictVersion = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200, pattern=r"\S")]


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class SourceSelection(Boundary):
    # JSON UUID strings are parsed at the HTTP boundary; domain values are strict.
    source_id: UUID
    generation: int = Field(strict=True, ge=1, le=2_147_483_647)
    processing_version: StrictVersion


class ContextCreate(Boundary):
    idempotency_key: str = Field(strict=True, min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    selected_sources: list[SourceSelection] = Field(min_length=1, max_length=20)
    learner: LearnerPreferences

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len({item.source_id for item in self.selected_sources}) != len(self.selected_sources):
            raise ValueError("Duplicate selected source")
        return self


class ContextView(Boundary):
    id: UUID
    tenant_id: str
    project_id: UUID
    created_at: datetime
    request: GenerationRequest
    tutorial_snapshots: list[TutorialEvidenceSnapshot] = Field(min_length=1, max_length=20)
