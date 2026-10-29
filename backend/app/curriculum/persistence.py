"""HTTP inputs and saved curriculum context/draft projections."""

from datetime import datetime
import json
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .contracts import AssignmentContent, BoundAssignment, GenerationRequest, LearnerPreferences, TutorialEvidenceSnapshot


MAX_CONTEXT_BYTES = 4_000_000
MAX_DRAFT_STORAGE_BYTES = 300_000
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


class DraftCreate(Boundary):
    idempotency_key: str = Field(strict=True, min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    content: AssignmentContent

    @field_validator("content", mode="before")
    @classmethod
    def parse_content(cls, value):
        # HTTP JSON is decoded into Python values before validation. Explicitly
        # parse JSON UUID text while retaining strict numeric/boolean validation.
        if isinstance(value, dict):
            return AssignmentContent.model_validate_json(json.dumps(value), strict=True)
        return value


class DraftReplace(DraftCreate):
    expected_revision: int = Field(strict=True, ge=1, le=2_147_483_646)


class DraftRevisionView(Boundary):
    id: UUID
    tenant_id: str
    project_id: UUID
    context_id: UUID
    revision: int = Field(ge=1)
    created_at: datetime
    assignment: BoundAssignment
