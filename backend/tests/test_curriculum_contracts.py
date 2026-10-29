"""Synthetic assignment data; no model, service, stored source or user data."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.chat.contracts import EvidenceView
from app.curriculum.contracts import (
    MAX_DRAFT_BYTES,
    AssignmentDraft,
    DocumentationExcerpt,
    DocumentationSnapshot,
    GenerationRequest,
    LearnerPreferences,
    SourceVersionPin,
    TutorialEvidenceSnapshot,
)
from app.curriculum.validation import CurriculumValidationError, bind_assignment, parse_draft
from app.provenance import AsrOrigin, DescriptionOrigin, VisualOrigin


@pytest.fixture
def context():
    project, source, segment = uuid4(), uuid4(), uuid4()
    pin = SourceVersionPin(tenant_id="tenant-a", project_id=project, source_id=source,
                           generation=4, processing_version="transcript-chunks-v1:g4")
    request = GenerationRequest(
        tenant_id="tenant-a", project_id=project, selected_sources=[pin],
        learner=LearnerPreferences(experience="intermediate", difficulty="intermediate",
                                   language="tr", available_minutes=120,
                                   allow_prerequisites=False, allow_extensions=False,
                                   allow_external_documentation=False),
    )
    evidence = EvidenceView(
        segment_id=segment, source_id=source, source_filename="authored.vtt",
        start_ms=1000, end_ms=2000, text="Create a FastAPI route with a response model.",
        modality="transcript", processing_version=pin.processing_version, generation=4,
    )
    snapshot = TutorialEvidenceSnapshot(pin=pin, segments=[evidence])
    draft = AssignmentDraft(
        tenant_id="tenant-a", project_id=project, schema_version="assignment-draft-v1",
        title="A small API", scenario="Expose a synthetic reading list.", estimated_minutes=90,
        objectives=[{"id": "routes", "description": "Define an API route.",
                     "tutorial_segment_ids": [segment]}],
        requirements=[{"id": "list-books", "label": "covered", "description": "List books.",
                       "objective_ids": ["routes"], "tutorial_segment_ids": [segment],
                       "documentation_excerpt_ids": []}],
        constraints=["Use synthetic data."], deliverables=["Python source files."],
        acceptance_criteria=[{"id": "returns-list", "description": "GET /books returns a list.",
                              "requirement_ids": ["list-books"]}],
        rubric=[{"id": "clarity", "description": "Describe the API clearly.",
                 "acceptance_criterion_ids": ["returns-list"]}],
        hints=[{"id": "route-hint", "level": 1, "text": "Review the route decorator.",
                "requirement_ids": ["list-books"]}],
    )
    return request, draft, snapshot


def bind(context, documents=None, hosts=frozenset()):
    request, draft, snapshot = context
    return bind_assignment(request, draft, [snapshot], documents or [], allowed_document_hosts=hosts)


def document(context, *, url="https://docs.example.test/api"):
    request, _, _ = context
    text = "An official synthetic response-model explanation."
    return DocumentationSnapshot(
        tenant_id=request.tenant_id, project_id=request.project_id, id=uuid4(), url=url,
        retrieved_at=datetime(2026, 10, 29, tzinfo=timezone.utc), detected_version=None,
        content_sha256="a" * 64,
        excerpts=[DocumentationExcerpt(id=uuid4(), text=text,
                                       content_sha256=sha256(text.encode()).hexdigest())],
    )


def external_context(context, label="extension"):
    request, draft, snapshot = context
    request.learner.allow_prerequisites = True
    request.learner.allow_extensions = True
    request.learner.allow_external_documentation = True
    doc = document(context)
    draft.requirements[0].label = label
    draft.requirements[0].tutorial_segment_ids = []
    draft.requirements[0].documentation_excerpt_ids = [doc.excerpts[0].id]
    return (request, draft, snapshot), doc


def test_resolves_existing_projection_and_accepts_retained_generation(context):
    request, draft, snapshot = context
    snapshot.segments[0].asr_origin = AsrOrigin(
        job_id=uuid4(), generation=2, provider="local-whisper", model="base",
        revision="pinned", profile="local-asr-v1", engine="1.0.0", requested_language="en",
        assembly_version="vtt-v1", completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    result = bind(context)
    assert result.tutorial_evidence == snapshot.segments
    assert result.tutorial_evidence[0].generation == 4
    assert result.tutorial_evidence[0].asr_origin.machine_generated is True
    # Inputs can change after a boundary call without rewriting its accepted result.
    snapshot.segments[0].asr_origin.model = "changed"
    snapshot.segments[0].text = "changed"
    draft.title = "changed"
    request.learner.available_minutes = 1
    assert result.draft.title == "A small API"
    assert result.tutorial_evidence[0].text.startswith("Create a FastAPI")
    assert result.tutorial_evidence[0].asr_origin.model == "base"


def test_preserves_point_frame_and_unreviewed_visual_origin(context):
    request, _, snapshot = context
    snapshot.pin.processing_version = "visual-ocr-chunks-v1:g4"
    segment = snapshot.segments[0]
    segment.processing_version = snapshot.pin.processing_version
    segment.modality = "frame"
    segment.start_ms = segment.end_ms = 0
    segment.frame_id = uuid4()
    segment.visual_origin = VisualOrigin(
        job_id=uuid4(), generation=1, profile="local-visual-v1:" + "a" * 64,
        language="en", engines={"ocr": "tesseract"}, checkpoint_version="visual-checkpoint-v1",
        prepared_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    request.selected_sources[0].processing_version = snapshot.pin.processing_version
    bound = bind(context).tutorial_evidence[0]
    assert bound.start_ms == bound.end_ms == 0
    assert bound.frame_id == segment.frame_id
    assert bound.visual_origin.human_reviewed is False


def visual_context(context, *, described=False):
    request, _, snapshot = context
    version = ("visual-evidence-chunks-v2:g4" if described else "visual-ocr-chunks-v1:g4")
    request.selected_sources[0].processing_version = version
    snapshot.pin.processing_version = version
    segment = snapshot.segments[0]
    segment.processing_version = version
    segment.modality = "frame"
    segment.start_ms = segment.end_ms = 0
    segment.frame_id = uuid4()
    segment.visual_origin = VisualOrigin(
        job_id=uuid4(), generation=1, profile="local-visual-v1:" + "a" * 64,
        language="en", engines={"ocr": "tesseract"}, checkpoint_version="visual-checkpoint-v1",
        prepared_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        description=(DescriptionOrigin(
            job_id=uuid4(), generation=2, provider="ollama-local", model="qwen3.5:4b",
            model_digest="b" * 64, engine="0.20.0", prompt_version="retained-frame-description-v1",
            completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        ) if described else None),
    )
    return context


@pytest.mark.parametrize("described,wrong_version", [
    (False, "transcript-chunks-v1:g4"),
    (False, "visual-evidence-chunks-v2:g4"),
    (True, "transcript-chunks-v1:g4"),
    (True, "visual-ocr-chunks-v1:g4"),
])
def test_visual_origin_cannot_be_bound_to_another_parser(context, described, wrong_version):
    request, _, snapshot = visual_context(context, described=described)
    request.selected_sources[0].processing_version = wrong_version
    snapshot.pin.processing_version = wrong_version
    snapshot.segments[0].processing_version = wrong_version
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "invalid_tutorial_snapshot"


def test_mixed_visual_provenance_retains_exact_description_identity(context):
    result = bind(visual_context(context, described=True))
    origin = result.tutorial_evidence[0].visual_origin
    assert origin.description == context[2].segments[0].visual_origin.description
    assert result.tutorial_evidence[0].processing_version == "visual-evidence-chunks-v2:g4"


@pytest.mark.parametrize("keep_visual_origin", [False, True])
def test_frame_cannot_claim_audio_transcription_origin(context, keep_visual_origin):
    visual_context(context)
    segment = context[2].segments[0]
    if not keep_visual_origin:
        segment.visual_origin = None
    segment.asr_origin = AsrOrigin(
        job_id=uuid4(), generation=1, provider="local-whisper", model="base",
        revision="pinned", profile="local-asr-v1", engine="1.0.0", requested_language="en",
        assembly_version="vtt-v1", completed_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "invalid_tutorial_snapshot"


@pytest.mark.parametrize("target", ["draft", "request_pin", "snapshot"])
@pytest.mark.parametrize("field,value", [("tenant_id", "foreign-tenant"), ("project_id", uuid4())])
def test_rejects_foreign_scope(context, target, field, value):
    request, draft, snapshot = context
    instance = {"draft": draft, "request_pin": request.selected_sources[0], "snapshot": snapshot.pin}[target]
    setattr(instance, field, value)
    with pytest.raises(CurriculumValidationError):
        bind(context)


@pytest.mark.parametrize("field,value", [("source_id", uuid4()), ("generation", 3),
                                        ("processing_version", "other-version")])
def test_rejects_unselected_or_changed_source_pin(context, field, value):
    request, _, snapshot = context
    # Separate the trusted and requested pins, which Pydantic already revalidates.
    snapshot.pin = snapshot.pin.model_copy(deep=True)
    setattr(snapshot.pin, field, value)
    for segment in snapshot.segments:
        setattr(segment, field, value)
    assert getattr(request.selected_sources[0], field) != value
    with pytest.raises(CurriculumValidationError, match="could not be validated") as error:
        bind(context)
    assert error.value.code == "source_pin_mismatch"


@pytest.mark.parametrize("field,value", [("source_id", uuid4()), ("generation", 5),
                                        ("processing_version", "unpublished")])
def test_rejects_segment_provenance_mismatch(context, field, value):
    setattr(context[2].segments[0], field, value)
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "invalid_tutorial_snapshot"


def test_rejects_missing_or_duplicate_trusted_snapshots(context):
    request, draft, snapshot = context
    with pytest.raises(CurriculumValidationError) as error:
        bind_assignment(request, draft, [], [])
    assert error.value.code == "missing_source_snapshot"
    with pytest.raises(CurriculumValidationError) as error:
        bind_assignment(request, draft, [snapshot, snapshot], [])
    assert error.value.code == "duplicate_source_snapshot"
    snapshot.segments.append(snapshot.segments[0])
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "invalid_tutorial_snapshot"


def test_rejects_same_segment_identity_in_different_selected_sources(context):
    request, draft, snapshot = context
    second = snapshot.model_copy(deep=True)
    second.pin.source_id = uuid4()
    second.segments[0].source_id = second.pin.source_id
    request.selected_sources.append(second.pin)
    with pytest.raises(CurriculumValidationError) as error:
        bind_assignment(request, draft, [snapshot, second], [])
    assert error.value.code == "duplicate_evidence"


def test_missing_evidence_is_not_replaced_by_other_snapshot_content(context):
    context[1].objectives[0].tutorial_segment_ids = [uuid4()]
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "missing_tutorial_evidence"


@pytest.mark.parametrize("field,value", [("available_minutes", "120"), ("available_minutes", True),
                                        ("allow_extensions", "false"), ("allow_extensions", 0)])
def test_preferences_reject_coerced_numbers_and_booleans(context, field, value):
    data = context[0].learner.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        LearnerPreferences.model_validate(data)


@pytest.mark.parametrize("group,field,value", [
    ("objectives", "description", "   "),
    ("objectives", "tutorial_segment_ids", []),
    ("requirements", "objective_ids", ["unknown"]),
    ("requirements", "tutorial_segment_ids", []),
    ("acceptance_criteria", "requirement_ids", ["unknown"]),
    ("rubric", "acceptance_criterion_ids", ["unknown"]),
    ("hints", "requirement_ids", ["unknown"]),
    ("hints", "level", True),
    ("hints", "level", 2),
])
def test_draft_rejects_invalid_content_and_cross_references(context, group, field, value):
    data = context[1].model_dump()
    data[group][0][field] = value
    with pytest.raises(ValidationError):
        AssignmentDraft.model_validate(data)


@pytest.mark.parametrize("group", ["objectives", "requirements", "acceptance_criteria", "rubric", "hints"])
def test_draft_rejects_duplicate_local_identity(context, group):
    data = context[1].model_dump()
    data[group].append(deepcopy(data[group][0]))
    with pytest.raises(ValidationError):
        AssignmentDraft.model_validate(data)


def test_json_boundary_rejects_unknown_nested_fields_and_hides_raw_model_text(context):
    payload = context[1].model_dump(mode="json")
    payload["requirements"][0]["injected_instructions"] = "SECRET MODEL CONTENT"
    import json
    with pytest.raises(CurriculumValidationError) as error:
        parse_draft(json.dumps(payload))
    assert error.value.code == "invalid_draft"
    assert "SECRET" not in str(error.value)
    assert error.value.__cause__ is None


def test_json_boundary_accepts_uuid_strings_without_python_coercion(context):
    assert parse_draft(context[1].model_dump_json()) == context[1]


@pytest.mark.parametrize("nested", [False, True])
def test_json_boundary_rejects_duplicate_object_keys(context, nested):
    payload = context[1].model_dump_json()
    if nested:
        payload = payload.replace('"level":1', '"level":2,"level":1')
    else:
        payload = payload.replace('"title":"A small API"', '"title":"SECRET","title":"A small API"')
    with pytest.raises(CurriculumValidationError) as error:
        parse_draft(payload)
    assert error.value.code == "invalid_draft"
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("unassessed", ["requirement", "criterion"])
def test_draft_requires_complete_acceptance_and_rubric_links(context, unassessed):
    data = context[1].model_dump()
    group = "requirements" if unassessed == "requirement" else "acceptance_criteria"
    item = deepcopy(data[group][0])
    item["id"] = "unassessed"
    data[group].append(item)
    with pytest.raises(ValidationError):
        AssignmentDraft.model_validate(data)


def test_evidence_budget_fails_before_reading_later_snapshots(context):
    request, draft, snapshot = context
    snapshot.segments = [
        snapshot.segments[0].model_copy(update={"segment_id": uuid4(), "text": "x" * 10_000})
        for _ in range(51)
    ]
    # The unrelated invalid object must not be reached after the resource limit.
    with pytest.raises(CurriculumValidationError) as error:
        bind_assignment(request, draft, [snapshot, object()], [])
    assert error.value.code == "evidence_too_large"


@pytest.mark.parametrize("payload", [b"{", b"\xff", "x" * (MAX_DRAFT_BYTES + 1), None])
def test_json_boundary_rejects_malformed_and_oversized_payload(payload):
    with pytest.raises(CurriculumValidationError):
        parse_draft(payload)


def test_revalidates_constructed_and_mutated_pydantic_values(context):
    request, draft, snapshot = context
    draft.requirements[0].tutorial_segment_ids.clear()
    bypassed = AssignmentDraft.model_construct(**draft.__dict__)
    with pytest.raises(CurriculumValidationError) as error:
        bind_assignment(request, bypassed, [snapshot], [])
    assert error.value.code == "invalid_draft"


def test_revalidates_nested_existing_evidence_models(context):
    context[2].segments[0].start_ms = True
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "invalid_tutorial_snapshot"


def test_draft_effort_must_fit_explicit_learner_time(context):
    context[0].learner.available_minutes = 60
    with pytest.raises(CurriculumValidationError) as error:
        bind(context)
    assert error.value.code == "effort_exceeded"


@pytest.mark.parametrize("label,permission,code", [
    ("prerequisite", "allow_prerequisites", "prerequisites_forbidden"),
    ("extension", "allow_extensions", "extensions_forbidden"),
])
def test_external_topics_require_their_explicit_permission(context, label, permission, code):
    context, doc = external_context(context, label)
    setattr(context[0].learner, permission, False)
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == code


def test_documentation_requires_permission_and_cannot_be_tutorial_evidence(context):
    context, doc = external_context(context)
    context[0].learner.allow_external_documentation = False
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "documentation_forbidden"
    context[0].learner.allow_external_documentation = True
    context[1].requirements[0].label = "covered"
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "invalid_draft"


def test_official_doc_binding_keeps_separate_exact_metadata_and_is_detached(context):
    context, doc = external_context(context)
    result = bind(context, [doc], frozenset({"docs.example.test"}))
    bound = result.documentation_snapshots[0]
    assert bound == doc
    assert bound.detected_version is None
    assert result.tutorial_evidence[0].source_id == context[2].pin.source_id
    doc.excerpts[0].text = "changed after binding"
    assert bound.excerpts[0].text.startswith("An official")


@pytest.mark.parametrize("url", [
    "http://docs.example.test/api", "https://other.example.test/api",
    "https://docs.example.test.evil.test/api", "https://user@docs.example.test/api",
    "https://user:secret@docs.example.test/api", "https://docs.example.test:443/api",
    "https://docs.example.test./api", "https://DOCS.EXAMPLE.TEST/api",
    "https://docs.example.test\\@evil.test/api", "https://docs.example.test/\napi",
    "https://127.0.0.1/api", "file:///etc/passwd", "//docs.example.test/api",
])
def test_document_metadata_rejects_unsafe_or_nonexact_hosts(context, url):
    context, doc = external_context(context)
    doc.url = url
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test", "127.0.0.1"}))
    assert error.value.code == "documentation_host_forbidden"


@pytest.mark.parametrize("field,value", [("tenant_id", "tenant-b"), ("project_id", uuid4())])
def test_document_scope_cannot_cross_projects_or_tenants(context, field, value):
    context, doc = external_context(context)
    setattr(doc, field, value)
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "scope_mismatch"


def test_doc_snapshot_requires_explicit_allowlist_and_matching_excerpt(context):
    context, doc = external_context(context)
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc])
    assert error.value.code == "documentation_host_forbidden"
    context[1].requirements[0].documentation_excerpt_ids = [uuid4()]
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "missing_documentation_evidence"


def test_duplicate_document_and_excerpt_identities_are_rejected(context):
    context, doc = external_context(context)
    hosts = frozenset({"docs.example.test"})
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc, doc], hosts)
    assert error.value.code == "duplicate_documentation_snapshot"
    duplicate = doc.model_copy(deep=True)
    duplicate.id = uuid4()
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc, duplicate], hosts)
    assert error.value.code == "duplicate_documentation_evidence"


def test_document_digest_and_retrieval_timezone_are_revalidated(context):
    context, doc = external_context(context)
    doc.excerpts[0].text = "a changed excerpt"
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "invalid_documentation_snapshot"
    doc = document(context)
    doc.retrieved_at = datetime(2026, 10, 29)
    with pytest.raises(CurriculumValidationError) as error:
        bind(context, [doc], frozenset({"docs.example.test"}))
    assert error.value.code == "invalid_documentation_snapshot"
