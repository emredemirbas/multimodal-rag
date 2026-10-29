"""Bounded assignment values and trusted evidence inputs.

Nested objective/requirement values belong to their scoped draft, not independent
records. A scope on a DTO does not establish membership or authorize a read.
"""

from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..chat.contracts import EvidenceView
from ..models import TenantId


MAX_DRAFT_BYTES = 256_000
MAX_EVIDENCE_SEGMENTS = 500
MAX_EVIDENCE_CHARACTERS = 500_000

Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r"\S")]
LocalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Version = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", revalidate_instances="always")


class ScopedContract(Contract):
    tenant_id: TenantId
    project_id: UUID


class SourceVersionPin(ScopedContract):
    source_id: UUID
    generation: int = Field(ge=1)
    processing_version: Version


class LearnerPreferences(Contract):
    experience: Literal["beginner", "intermediate", "advanced"]
    difficulty: Literal["beginner", "intermediate", "advanced"]
    language: Literal["en", "tr"]
    available_minutes: int = Field(ge=1, le=10_080)
    allow_prerequisites: bool
    allow_extensions: bool
    allow_external_documentation: bool


class GenerationRequest(ScopedContract):
    selected_sources: list[SourceVersionPin] = Field(min_length=1, max_length=20)
    learner: LearnerPreferences

    @model_validator(mode="after")
    def valid_selection(self) -> Self:
        if len({pin.source_id for pin in self.selected_sources}) != len(self.selected_sources):
            raise ValueError("Duplicate selected source")
        if any((pin.tenant_id, pin.project_id) != (self.tenant_id, self.project_id)
               for pin in self.selected_sources):
            raise ValueError("Invalid selected source scope")
        return self


class LearningObjective(Contract):
    id: LocalId
    description: Text
    tutorial_segment_ids: list[UUID] = Field(min_length=1, max_length=10)


class Requirement(Contract):
    id: LocalId
    label: Literal["covered", "prerequisite", "extension"]
    description: Text
    objective_ids: list[LocalId] = Field(min_length=1, max_length=20)
    tutorial_segment_ids: list[UUID] = Field(max_length=10)
    documentation_excerpt_ids: list[UUID] = Field(max_length=10)

    @model_validator(mode="after")
    def evidence_kind(self) -> Self:
        if self.label == "covered" and not self.tutorial_segment_ids:
            raise ValueError("Covered requirement needs tutorial evidence")
        if self.label != "covered" and not self.documentation_excerpt_ids:
            raise ValueError("External requirement needs documentation evidence")
        return self


class AcceptanceCriterion(Contract):
    id: LocalId
    description: Text
    requirement_ids: list[LocalId] = Field(min_length=1, max_length=20)


class RubricCriterion(Contract):
    id: LocalId
    description: Text
    acceptance_criterion_ids: list[LocalId] = Field(min_length=1, max_length=50)


class DraftHint(Contract):
    id: LocalId
    level: int = Field(ge=1, le=10)
    text: Text
    requirement_ids: list[LocalId] = Field(min_length=1, max_length=20)


def _unique(values: list) -> bool:
    return len(set(values)) == len(values)


class AssignmentContent(Contract):
    """Unscoped editable content; scope is supplied by the application."""

    schema_version: Literal["assignment-draft-v1"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")]
    scenario: Text
    estimated_minutes: int = Field(ge=1, le=10_080)
    objectives: list[LearningObjective] = Field(min_length=1, max_length=20)
    requirements: list[Requirement] = Field(min_length=1, max_length=50)
    constraints: list[Text] = Field(max_length=20)
    deliverables: list[Text] = Field(min_length=1, max_length=20)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1, max_length=50)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=20)
    hints: list[DraftHint] = Field(max_length=10)

    @model_validator(mode="after")
    def references(self) -> Self:
        groups = (self.objectives, self.requirements, self.acceptance_criteria, self.rubric, self.hints)
        if any(not _unique([item.id for item in group]) for group in groups):
            raise ValueError("Duplicate draft identity")
        objectives = {item.id for item in self.objectives}
        requirements = {item.id for item in self.requirements}
        criteria = {item.id for item in self.acceptance_criteria}
        links = [(item.objective_ids, objectives) for item in self.requirements]
        links += [(item.requirement_ids, requirements) for item in self.acceptance_criteria]
        links += [(item.acceptance_criterion_ids, criteria) for item in self.rubric]
        links += [(item.requirement_ids, requirements) for item in self.hints]
        if any(not _unique(ids) or not set(ids) <= targets for ids, targets in links):
            raise ValueError("Invalid draft reference")
        assessed_requirements = {key for item in self.acceptance_criteria for key in item.requirement_ids}
        rubric_criteria = {key for item in self.rubric for key in item.acceptance_criterion_ids}
        if assessed_requirements != requirements or rubric_criteria != criteria:
            raise ValueError("Incomplete acceptance or rubric references")
        for item in [*self.objectives, *self.requirements]:
            if not _unique(item.tutorial_segment_ids):
                raise ValueError("Duplicate tutorial reference")
        if any(not _unique(item.documentation_excerpt_ids) for item in self.requirements):
            raise ValueError("Duplicate documentation reference")
        if [item.level for item in self.hints] != list(range(1, len(self.hints) + 1)):
            raise ValueError("Invalid hint order")
        if len(self.model_dump_json().encode("utf-8")) > MAX_DRAFT_BYTES:
            raise ValueError("Draft exceeds the payload limit")
        return self


class AssignmentDraft(AssignmentContent, ScopedContract):
    """Content bound to the authenticated tenant and project by application code."""


class TutorialEvidenceSnapshot(Contract):
    """Application-supplied published evidence subset for one exact source pin."""

    pin: SourceVersionPin
    segments: list[EvidenceView] = Field(min_length=1, max_length=MAX_EVIDENCE_SEGMENTS)

    @model_validator(mode="after")
    def consistent_segments(self) -> Self:
        if not _unique([segment.segment_id for segment in self.segments]):
            raise ValueError("Duplicate evidence identity")
        for segment in self.segments:
            if (segment.source_id != self.pin.source_id or segment.generation != self.pin.generation
                    or segment.processing_version != self.pin.processing_version):
                raise ValueError("Invalid evidence source version")
            if (not segment.source_filename.strip() or len(segment.source_filename) > 255
                    or not segment.text.strip() or len(segment.text) > 10_000
                    or segment.start_ms < 0 or segment.end_ms < segment.start_ms
                    or segment.modality not in {"transcript", "frame"}
                    or (segment.modality == "frame" and segment.asr_origin is not None)
                    or (segment.modality != "frame" and (segment.end_ms == segment.start_ms
                                                         or segment.frame_id is not None
                                                         or segment.visual_origin is not None))):
                raise ValueError("Invalid evidence projection")
            if segment.visual_origin is not None:
                origin = segment.visual_origin
                parser = ("visual-evidence-chunks-v2" if origin.description is not None
                          else "visual-ocr-chunks-v1")
                if (segment.frame_id is None or segment.start_ms != segment.end_ms
                        or segment.processing_version != f"{parser}:g{segment.generation}"
                        or origin.generation >= segment.generation
                        or (origin.description is not None
                            and not origin.generation < origin.description.generation < segment.generation)):
                    raise ValueError("Invalid visual evidence projection")
        return self


class DocumentationExcerpt(Contract):
    id: UUID
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000, pattern=r"\S")]
    content_sha256: Digest

    @model_validator(mode="after")
    def valid_digest(self) -> Self:
        if sha256(self.text.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("Invalid documentation excerpt digest")
        return self


class DocumentationSnapshot(ScopedContract):
    """Already authorized official documentation; this contract performs no fetch."""

    id: UUID
    url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    retrieved_at: datetime
    detected_version: Version | None
    content_sha256: Digest
    excerpts: list[DocumentationExcerpt] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_snapshot(self) -> Self:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("Documentation retrieval time needs a timezone")
        if not _unique([excerpt.id for excerpt in self.excerpts]):
            raise ValueError("Duplicate documentation excerpt identity")
        return self


class BoundAssignment(ScopedContract):
    """Resolved identities, not membership authorization or semantic approval."""

    draft: AssignmentDraft
    tutorial_evidence: list[EvidenceView] = Field(max_length=MAX_EVIDENCE_SEGMENTS)
    documentation_snapshots: list[DocumentationSnapshot] = Field(max_length=20)
