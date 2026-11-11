"""Real LangGraph with authored replies; no model or hosted tracing service."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from langsmith.run_helpers import get_tracing_context
import pytest

from app.curriculum.execution import StageFailure, StageInput, StageLeaseLost
from app.curriculum.local_provider import JsonModelResponse, LocalCurriculumProvider, _json_bytes
from app.curriculum.objectives import (
    BatchExtraction, CompactExtraction, MAX_BATCHES, MAX_SLICE_BYTES, checked_context, context_digest,
    extract_spec, parse_value, plan_batches, validate_extraction,
)
from app.curriculum.persistence import ContextView
from app.curriculum.run_contracts import CheckpointView, RunClaim, RunView
from app.curriculum.workflow import TutorialAssignmentWorkflow, WORKFLOW_VERSION
from app.provenance import AsrOrigin
from test_curriculum_contracts import context, visual_context
from test_curriculum_local_provider import identity


def authored_canonical_extraction(body):
    """Old canonical checkpoint shape, independent of the new model protocol."""
    item = body["slices"][0]
    return {"goals": [{"id": "route", "description": "Define an API route.",
                        "anchors": [{"slice_id": item["id"], "quote": item["text"][:30]}]}],
            "coverage": [{"slice_id": value["id"], "status": "supported" if index == 0 else "insufficient_evidence",
                          "goal_ids": ["route"] if index == 0 else [],
                          "reason": None if index == 0 else "No additional goal in this authored reply."}
                         for index, value in enumerate(body["slices"])]}


def authored_reply(body):
    """Synthetic protocol peer, not a second implementation or model substitute."""
    if body["stage"] == "extract":
        item = body["slices"][0]
        return {"goals": [{"description": "Define an API route.",
                            "anchors": [{"slice_id": item["id"], "quote": item["text"][:30]}]}],
                "insufficient": [{"slice_id": value["id"], "reason": "No additional goal in this authored reply."}
                                 for value in body["slices"][1:]]}
    if body["stage"] == "select":
        return {"goal_ids": [body["goals"][0]["id"]]}
    objectives = body["objectives"]
    return {
        "schema_version": "assignment-draft-v1", "title": "A small authored API",
        "scenario": "Expose synthetic data.", "estimated_minutes": 30, "objectives": objectives,
        "requirements": [{"id": "route", "label": "covered", "description": "Define the route.",
                          "objective_ids": [item["id"] for item in objectives],
                          "tutorial_segment_ids": sorted({key for item in objectives for key in item["tutorial_segment_ids"]}),
                          "documentation_excerpt_ids": []}],
        "constraints": ["Use synthetic data."], "deliverables": ["Python source files."],
        "acceptance_criteria": [{"id": "response", "description": "The route returns a response.", "requirement_ids": ["route"]}],
        "rubric": [{"id": "clarity", "description": "Describe the route.", "acceptance_criterion_ids": ["response"]}],
        "hints": [{"id": "decorator", "level": 1, "text": "Review the decorator.", "requirement_ids": ["route"]}],
    }


class AuthoredCalls:
    def __init__(self):
        self.provider = LocalCurriculumProvider("http://127.0.0.1:1", identity())
        self.requests = []
        self.reply = authored_reply
        self.failure = None
        self.lost = False

    def invoke(self, claim, spec):
        assert get_tracing_context()["enabled"] is False
        self.requests.append(json.loads(spec.user))
        if self.failure:
            raise self.failure
        if self.lost:
            return None
        reply = self.reply(self.requests[-1])
        return JsonModelResponse(identity=self.provider.identity, input_sha256=self.provider.prepare(spec).input_sha256,
                                 content=json.dumps(reply) if not isinstance(reply, str) else reply,
                                 input_tokens=123, output_tokens=35, duration_ms=1)


class Session:
    """Detached persisted-boundary harness; database tests exercise the SQL fence."""
    def __init__(self, supplied):
        request, _, snapshot = supplied
        now = datetime.now(timezone.utc)
        self.context = ContextView(id=uuid4(), tenant_id=request.tenant_id, project_id=request.project_id,
                                   created_at=now, request=request, tutorial_snapshots=[snapshot])
        self.run = RunView(id=uuid4(), tenant_id=request.tenant_id, project_id=request.project_id,
            context_id=self.context.id, actor_user_id=uuid4(), workflow_version=WORKFLOW_VERSION, status="running",
            attempt_count=1, failure_count=0, checkpoint_seq=0, available_at=now, lease_expires_at=now,
            created_at=now, updated_at=now, finished_at=None, failure_code=None)
        self.calls = AuthoredCalls()
        self.checkpoints = []

    def advance(self):
        claim = RunClaim(tenant_id=self.run.tenant_id, project_id=self.run.project_id, run_id=self.run.id,
                         lease_token=uuid4(), attempt_number=self.run.attempt_count)
        before = len(self.calls.requests)
        # Reconstruct graph every delivery, as after a process restart.
        workflow = TutorialAssignmentWorkflow(self.calls)
        assert workflow.graph.checkpointer is None
        result = workflow(StageInput(self.run, self.context, tuple(self.checkpoints), claim))
        assert len(self.calls.requests) - before <= 1
        if result.checkpoint:
            cp = result.checkpoint
            self.checkpoints.append(CheckpointView(**cp.model_dump(), tenant_id=self.run.tenant_id,
                project_id=self.run.project_id, run_id=self.run.id, workflow_version=WORKFLOW_VERSION,
                attempt_number=self.run.attempt_count, created_at=self.run.created_at,
                content_sha256=sha256(_json_bytes(cp.payload)).hexdigest()))
            self.run.checkpoint_seq += 1
        self.run.attempt_count += 1
        return result

    def finish(self):
        for _ in range(25):
            result = self.advance()
            if result.content is not None:
                return result.content
        pytest.fail("The bounded workflow did not finish")


@pytest.fixture
def session(context):
    return Session(context)


def test_lossless_utf8_slices_keep_exact_ids_offsets_and_complete_source(session):
    segment = session.context.tutorial_snapshots[0].segments[0]
    segment.text = ("ş😀\\\"\nAPI route. " * 380)[:9000]
    batches = plan_batches(session.context)
    slices = [item for batch in batches for item in batch.slices]
    assert 1 < len(batches) <= MAX_BATCHES
    assert "".join(item.text for item in slices) == segment.text
    for index, item in enumerate(slices):
        assert item.id == f"s{index:05d}" and len(item.text.encode()) <= MAX_SLICE_BYTES
        assert item.text == segment.text[item.start_char:item.end_char]
        assert item.segment_id == segment.segment_id and item.source_id == segment.source_id
        assert item.processing_version == segment.processing_version and item.origin == "uploaded_transcript"
    assert plan_batches(session.context) == batches


def test_all_batch_overflow_fails_before_any_inference(session):
    segment = session.context.tutorial_snapshots[0].segments[0]
    segment.text = "x" * 10_000
    for _ in range(20):
        other = deepcopy(segment)
        other.segment_id = uuid4()
        session.context.tutorial_snapshots[0].segments.append(other)
    with pytest.raises(StageFailure):
        session.advance()
    assert session.calls.requests == [] and session.checkpoints == []


@pytest.mark.parametrize("described", [False, True])
def test_visual_interpretation_remains_unreviewed_and_preserves_original_identity(context, described):
    transformed = Session(visual_context(context, described=described))
    original = transformed.context.tutorial_snapshots[0].segments[0]
    item = plan_batches(transformed.context)[0].slices[0]
    assert item.origin == ("unreviewed_ocr_and_description" if described else "unreviewed_ocr")
    assert item.segment_id == original.segment_id and item.modality == "frame"
    assert transformed.finish().objectives[0].tutorial_segment_ids == [original.segment_id]


def test_asr_interpretation_is_labelled_without_replacing_published_generation(session):
    segment = session.context.tutorial_snapshots[0].segments[0]
    segment.asr_origin = AsrOrigin(job_id=uuid4(), generation=2, provider="local-whisper", model="base",
        revision="pinned", profile="local-asr-v1", engine="1.0.0", requested_language="en",
        assembly_version="vtt-v1", completed_at=datetime.now(timezone.utc))
    item = plan_batches(session.context)[0].slices[0]
    assert item.origin == "unreviewed_asr" and item.segment_id == segment.segment_id
    assert item.processing_version == segment.processing_version and segment.generation == 4
    assert session.finish().objectives[0].tutorial_segment_ids == [segment.segment_id]


@pytest.mark.parametrize("change", ["quote", "slice", "coverage-missing", "coverage-duplicate", "coverage-goal", "duplicate-goal", "foreign-field"])
def test_extraction_rejects_invented_quotes_ids_and_incomplete_coverage(session, change):
    batch = plan_batches(session.context)[0]
    body = {"stage": "extract", "slices": [item.model_dump(mode="json") for item in batch.slices]}
    result = authored_canonical_extraction(body)
    if change == "quote": result["goals"][0]["anchors"][0]["quote"] = "Unseen PRIVATE content"
    if change == "slice": result["goals"][0]["anchors"][0]["slice_id"] = "s99999"
    if change == "coverage-missing": result["coverage"] = []
    if change == "coverage-duplicate": result["coverage"] *= 2
    if change == "coverage-goal": result["coverage"][0]["goal_ids"] = ["other"]
    if change == "duplicate-goal": result["goals"] *= 2
    if change == "foreign-field": result["tenant_id"] = "foreign-tenant"
    with pytest.raises(ValueError):
        validate_extraction(batch, parse_value(BatchExtraction, json.dumps(result)))


def test_native_schema_only_offers_supplied_slice_ids_without_model_coverage(session):
    session.context.tutorial_snapshots[0].segments[0].text = "route " * 700
    batch = plan_batches(session.context)[0]
    spec = extract_spec(batch, session.context.request.learner)
    assert spec.prompt_version == "tutorial-objectives-v4" and spec.schema_version == "tutorial-objectives-json-v4"
    definitions = spec.output_schema["$defs"]
    expected = [item.id for item in batch.slices]
    assert len(expected) > 1
    for name in ("GoalAnchor", "InsufficientSlice"):
        assert definitions[name]["properties"]["slice_id"]["enum"] == expected
    assert set(definitions["ProposedGoal"]["properties"]) == {"description", "anchors"}
    assert set(definitions["InsufficientSlice"]["properties"]) == {"slice_id", "reason"}
    # Dynamic schema construction must not contaminate another source batch.
    assert "enum" not in CompactExtraction.model_json_schema()["$defs"]["GoalAnchor"]["properties"]["slice_id"]


@pytest.mark.parametrize("status,ids,reason", [
    ("supported", ["route"], "Native v1 incorrectly supplied an explanation."),
    ("supported", [], None), ("supported", ["route", "route"], None),
    ("insufficient_evidence", ["route"], "Not supported."),
    ("insufficient_evidence", [], None), ("insufficient_evidence", [], " "),
])
def test_status_invariants_remain_mandatory_after_native_schema_fix(session, status, ids, reason):
    value = {"goals": [], "coverage": [{"slice_id": "s00000", "status": status, "goal_ids": ids, "reason": reason}]}
    with pytest.raises(ValueError):
        parse_value(BatchExtraction, json.dumps(value))


def test_graph_extracts_selects_and_generates_with_exact_bound_evidence(session):
    assert session.advance().checkpoint.stage == "curriculum.initialized" and not session.calls.requests
    content = session.finish()
    assert [item["stage"] for item in session.calls.requests] == ["extract", "select", "generate"]
    assert [item.stage for item in session.checkpoints] == ["curriculum.initialized", "curriculum.extracted", "curriculum.selected"]
    assert content.objectives[0].id == "g00_goal0"
    assert content.objectives[0].tutorial_segment_ids == [session.context.tutorial_snapshots[0].segments[0].segment_id]
    assert session.checkpoints[-1].payload["selected_ids"] == ["g00_goal0"]
    assert session.checkpoints[1].payload["accepted"][0]["extraction"]["coverage"][0]["status"] == "supported"


def test_all_slices_are_extracted_once_and_omissions_remain_in_progress(session):
    segment = session.context.tutorial_snapshots[0].segments[0]
    segment.text = "Define a route. " * 620
    batches = plan_batches(session.context)
    content = session.finish()
    assert len(batches) > 1
    assert [item["batch"] for item in session.calls.requests if item["stage"] == "extract"] == list(range(len(batches)))
    progress = session.checkpoints[-1].payload
    assert len(progress["accepted"]) == len(batches) and progress["selected_ids"] == ["g00_goal0"]
    assert len(content.objectives) == 1
    assert sum(len(item["extraction"]["coverage"]) for item in progress["accepted"]) == sum(len(item.slices) for item in batches)


def test_maximum_plan_with_revision_still_has_finite_checkpoint_and_call_bounds(session):
    segment = session.context.tutorial_snapshots[0].segments[0]
    segment.text = "a" * (MAX_SLICE_BYTES * 4)
    session.context.tutorial_snapshots[0].segments = []
    for index in range(MAX_BATCHES):
        item = deepcopy(segment)
        item.segment_id = uuid4()
        item.start_ms, item.end_ms = index * 2000, index * 2000 + 1000
        session.context.tutorial_snapshots[0].segments.append(item)
    assert len(plan_batches(session.context)) == MAX_BATCHES
    session.calls.reply = lambda body: {"title": "Incomplete"} if body["stage"] == "generate" else authored_reply(body)
    assert session.finish().title == "A small authored API"
    assert len(session.calls.requests) == len(session.checkpoints) == 23
    assert len(session.checkpoints[-1].payload["accepted"]) == MAX_BATCHES


@pytest.mark.parametrize("field", ["description", "quote", "reason"])
def test_extraction_text_caps_are_utf8_bytes(session, field):
    batch = plan_batches(session.context)[0]
    value = authored_canonical_extraction({"stage": "extract", "slices": [item.model_dump(mode="json") for item in batch.slices]})
    if field == "description": value["goals"][0][field] = "ş" * 91
    if field == "quote": value["goals"][0]["anchors"][0][field] = "ş" * 121
    if field == "reason":
        value = {"goals": [], "coverage": [{"slice_id": batch.slices[0].id, "status": "insufficient_evidence",
                                           "goal_ids": [], "reason": "ş" * 91}]}
    with pytest.raises(ValueError):
        parse_value(BatchExtraction, json.dumps(value))


@pytest.mark.parametrize("bad", ["schema", "effort", "objective", "evidence", "extra-topic", "duplicate-json", "provider-invalid"])
def test_one_bounded_revision_can_fix_a_draft_without_reextracting(session, bad):
    def reply(body):
        value = authored_reply(body)
        if body["stage"] != "generate":
            return value
        if bad == "schema": return {"title": "PRIVATE incomplete draft"}
        if bad == "duplicate-json": return '{"title":"PRIVATE","title":"duplicate"}'
        if bad == "provider-invalid": raise StageFailure("invalid_output", retryable=False)
        if bad == "effort": value["estimated_minutes"] = 121
        if bad == "objective": value["objectives"][0]["description"] = "Unseen topic"
        if bad == "evidence": value["requirements"][0]["tutorial_segment_ids"] = [str(uuid4())]
        if bad == "extra-topic": value["requirements"][0].update(label="extension", documentation_excerpt_ids=[str(uuid4())])
        return value
    session.calls.reply = reply
    result = session.finish()
    assert result.title == "A small authored API"
    assert [item["stage"] for item in session.calls.requests] == ["extract", "select", "generate", "revise"]
    assert session.checkpoints[-1].stage == "curriculum.revision_pending"
    assert session.checkpoints[-1].payload["repair_used"] is True
    assert session.calls.requests[-1]["feedback"] in {"invalid_draft", "binding_failed", "objective_mismatch", "invalid_output"}


@pytest.mark.parametrize("mode", ["no-goals", "bad-extract", "unknown-selection", "duplicate-selection", "bad-revision", "oversize-repair"])
def test_unusable_outputs_stop_without_guessing_or_extra_revisions(session, mode):
    def reply(body):
        stage = body["stage"]
        if stage == "extract" and mode == "no-goals":
            return {"goals": [], "insufficient": [{"slice_id": item["id"], "reason": "No usable goal."}
                                                     for item in body["slices"]]}
        if stage == "extract" and mode == "bad-extract": return {"goals": [], "insufficient": []}
        if stage == "select" and mode == "unknown-selection": return {"goal_ids": ["g19_unknown"]}
        if stage == "select" and mode == "duplicate-selection": return {"goal_ids": ["g00_goal0", "g00_goal0"]}
        if stage in {"generate", "revise"} and mode == "bad-revision": return {"title": "PRIVATE invalid"}
        if stage == "generate" and mode == "oversize-repair": return {"raw": "x" * 6001}
        return authored_reply(body)
    session.calls.reply = reply
    with pytest.raises(StageFailure) as error:
        session.finish()
    assert error.value.code == "invalid_output" and not error.value.retryable
    phases = [item["stage"] for item in session.calls.requests]
    assert phases.count("revise") == (1 if mode == "bad-revision" else 0)
    if mode in {"no-goals", "bad-extract", "unknown-selection", "duplicate-selection"}:
        assert "generate" not in phases


@pytest.mark.parametrize("flag", ["allow_prerequisites", "allow_extensions", "allow_external_documentation"])
def test_external_permissions_stay_closed_until_approved_capture_exists(session, flag):
    setattr(session.context.request.learner, flag, True)
    with pytest.raises(StageFailure) as error:
        session.advance()
    assert error.value.code == "processing_unavailable" and session.calls.requests == []


@pytest.mark.parametrize("changed", ["tenant", "context", "source-pin", "text", "missing-cp", "hash", "scope", "workflow", "recipe", "selection", "extraction", "phase", "provider"])
def test_resume_rejects_tampered_scope_pins_or_accepted_progress_before_inference(session, changed):
    session.advance()
    session.advance()
    session.advance()
    before = len(session.calls.requests)
    cp = session.checkpoints[-1]
    if changed == "tenant": session.run.tenant_id = "foreign-tenant"
    if changed == "context": session.context.id = uuid4()
    if changed == "source-pin": session.context.request.selected_sources[0].generation += 1
    if changed == "text": session.context.tutorial_snapshots[0].segments[0].text = "Replaced source text"
    if changed == "missing-cp": session.checkpoints.pop()
    if changed == "hash": cp.content_sha256 = "b" * 64
    if changed == "scope": cp.project_id = uuid4()
    if changed == "workflow": cp.workflow_version = "foreign-v1"
    if changed == "recipe": cp.payload["recipe_sha256"] = "b" * 64
    if changed == "selection": cp.payload["selected_ids"] = ["g19_unknown"]
    if changed == "extraction": cp.payload["accepted"][0]["extraction"]["goals"][0]["anchors"][0]["quote"] = "Not in source"
    if changed == "phase": cp.payload["phase"] = "revise"
    if changed == "provider": session.calls.provider = LocalCurriculumProvider("http://127.0.0.1:1", identity(engine="0.40.4"))
    if changed in {"recipe", "selection", "extraction", "phase"}:
        cp.content_sha256 = sha256(_json_bytes(cp.payload)).hexdigest()
    with pytest.raises(StageFailure):
        session.advance()
    assert len(session.calls.requests) == before


def test_transient_failure_does_not_modify_accepted_progress_and_lease_loss_is_discarded(session):
    session.advance()
    session.calls.failure = StageFailure("provider_timeout", retryable=True)
    with pytest.raises(StageFailure) as error:
        session.advance()
    assert error.value.retryable and len(session.checkpoints) == 1
    session.calls.failure = None
    session.calls.lost = True
    with pytest.raises(StageLeaseLost):
        session.advance()
    assert len(session.checkpoints) == 1
    session.calls.lost = False
    assert session.finish().title == "A small authored API"


def test_hosted_tracing_stays_disabled_even_with_env_enabled(session, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    # A hosted client must not be created, including inside graph node threads.
    monkeypatch.setattr("langsmith.Client.__init__", lambda *_args, **_kwargs: pytest.fail("Hosted trace client created"))
    assert session.finish().title == "A small authored API"
    import os
    assert os.environ["LANGSMITH_TRACING"] == os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_context_hash_is_canonical_but_includes_source_provenance(session):
    first = context_digest(session.context)
    assert checked_context(session.context) == session.context
    session.context.tutorial_snapshots[0].segments[0].source_filename = "changed.vtt"
    assert context_digest(session.context) != first
