"""Pure structural/evidence binding; repository authorization remains mandatory."""

from ipaddress import ip_address
from json import loads
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from .contracts import (
    MAX_DRAFT_BYTES,
    MAX_EVIDENCE_CHARACTERS,
    MAX_EVIDENCE_SEGMENTS,
    AssignmentDraft,
    BoundAssignment,
    DocumentationSnapshot,
    GenerationRequest,
    TutorialEvidenceSnapshot,
)


class CurriculumValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        self.message = "The assignment context or evidence could not be validated."
        super().__init__(self.message)


def _unambiguous_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def parse_draft(payload: str | bytes) -> AssignmentDraft:
    """Parse bounded untrusted model JSON without exposing its text in errors."""
    try:
        if type(payload) not in {str, bytes}:
            raise ValueError()
        if len(payload.encode("utf-8") if isinstance(payload, str) else payload) > MAX_DRAFT_BYTES:
            raise CurriculumValidationError("draft_too_large")
        # Pydantic's JSON parser accepts duplicate keys. Reject ambiguity at every
        # nesting level before strict parsing (which preserves JSON UUID handling).
        loads(payload, object_pairs_hook=_unambiguous_object)
        return AssignmentDraft.model_validate_json(payload, strict=True)
    except CurriculumValidationError:
        raise
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise CurriculumValidationError("invalid_draft") from None


def _validated(contract: type[BaseModel], value, code: str):
    try:
        if not isinstance(value, contract):
            raise ValueError()
        # Rebuild, including nested existing provenance models: neither model_construct
        # nor mutation/model_copy may bypass this boundary. This also detaches inputs.
        return contract.model_validate(value.model_dump(warnings=False), strict=True)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise CurriculumValidationError(code) from None


def _approved_host(url: str, allowed_hosts: frozenset[str]) -> bool:
    if any(ord(character) <= 32 or ord(character) == 127 or character == "\\" for character in url):
        return False
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.port is not None
                or parsed.netloc != host or host not in allowed_hosts):
            return False
        try:
            ip_address(host)
        except ValueError:
            return True
        return False
    except ValueError:
        return False


def bind_assignment(
    request: GenerationRequest,
    draft: AssignmentDraft,
    tutorial_snapshots: list[TutorialEvidenceSnapshot],
    documentation_snapshots: list[DocumentationSnapshot],
    *,
    allowed_document_hosts: frozenset[str] = frozenset(),
) -> BoundAssignment:
    """Resolve model IDs only against caller-authorized published snapshots.

    No database/network/model operation occurs. The caller must authorize membership
    and recheck dependencies under its later commit/deletion fence. Retained older
    source generations are valid when they match the explicitly selected pins.
    """
    request = _validated(GenerationRequest, request, "invalid_request")
    draft = _validated(AssignmentDraft, draft, "invalid_draft")
    scope = (request.tenant_id, request.project_id)
    if (draft.tenant_id, draft.project_id) != scope:
        raise CurriculumValidationError("scope_mismatch")
    if draft.estimated_minutes > request.learner.available_minutes:
        raise CurriculumValidationError("effort_exceeded")
    if (type(tutorial_snapshots) is not list or len(tutorial_snapshots) > 20
            or type(documentation_snapshots) is not list or len(documentation_snapshots) > 20
            or type(allowed_document_hosts) is not frozenset
            or any(type(host) is not str or not host for host in allowed_document_hosts)):
        raise CurriculumValidationError("invalid_context")

    pins = {pin.source_id: pin for pin in request.selected_sources}
    seen_sources, evidence = set(), {}
    total_characters = 0
    for supplied in tutorial_snapshots:
        snapshot = _validated(TutorialEvidenceSnapshot, supplied, "invalid_tutorial_snapshot")
        pin = snapshot.pin
        if (pin.tenant_id, pin.project_id) != scope:
            raise CurriculumValidationError("scope_mismatch")
        if pin.source_id in seen_sources:
            raise CurriculumValidationError("duplicate_source_snapshot")
        if pins.get(pin.source_id) != pin:
            raise CurriculumValidationError("source_pin_mismatch")
        seen_sources.add(pin.source_id)
        for segment in snapshot.segments:
            if segment.segment_id in evidence:
                raise CurriculumValidationError("duplicate_evidence")
            evidence[segment.segment_id] = segment
            total_characters += len(segment.text)
            if len(evidence) > MAX_EVIDENCE_SEGMENTS or total_characters > MAX_EVIDENCE_CHARACTERS:
                raise CurriculumValidationError("evidence_too_large")
    if seen_sources != set(pins):
        raise CurriculumValidationError("missing_source_snapshot")
    documents, excerpts = {}, {}
    if documentation_snapshots and not request.learner.allow_external_documentation:
        raise CurriculumValidationError("documentation_forbidden")
    for supplied in documentation_snapshots:
        snapshot = _validated(DocumentationSnapshot, supplied, "invalid_documentation_snapshot")
        if (snapshot.tenant_id, snapshot.project_id) != scope:
            raise CurriculumValidationError("scope_mismatch")
        if not _approved_host(snapshot.url, allowed_document_hosts):
            raise CurriculumValidationError("documentation_host_forbidden")
        if snapshot.id in documents:
            raise CurriculumValidationError("duplicate_documentation_snapshot")
        documents[snapshot.id] = snapshot
        for excerpt in snapshot.excerpts:
            if excerpt.id in excerpts:
                raise CurriculumValidationError("duplicate_documentation_evidence")
            excerpts[excerpt.id] = snapshot.id

    tutorial_ids, document_ids = set(), set()
    for objective in draft.objectives:
        tutorial_ids.update(objective.tutorial_segment_ids)
    for requirement in draft.requirements:
        if requirement.label == "prerequisite" and not request.learner.allow_prerequisites:
            raise CurriculumValidationError("prerequisites_forbidden")
        if requirement.label == "extension" and not request.learner.allow_extensions:
            raise CurriculumValidationError("extensions_forbidden")
        tutorial_ids.update(requirement.tutorial_segment_ids)
        document_ids.update(requirement.documentation_excerpt_ids)
    if document_ids and not request.learner.allow_external_documentation:
        raise CurriculumValidationError("documentation_forbidden")
    if not tutorial_ids <= evidence.keys():
        raise CurriculumValidationError("missing_tutorial_evidence")
    if not document_ids <= excerpts.keys():
        raise CurriculumValidationError("missing_documentation_evidence")

    # Only cited projections leave this function. Models cannot invent metadata;
    # existing ASR/visual origins remain unchanged and input objects are detached.
    bound_documents = []
    for snapshot in documents.values():
        cited = [excerpt for excerpt in snapshot.excerpts if excerpt.id in document_ids]
        if cited:
            bound_documents.append(snapshot.model_copy(update={"excerpts": cited}))
    return BoundAssignment(
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        draft=draft,
        tutorial_evidence=[evidence[key] for key in sorted(tutorial_ids, key=str)],
        documentation_snapshots=bound_documents,
    )
