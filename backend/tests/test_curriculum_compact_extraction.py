"""Compact model replies become complete, source-bound application checkpoints."""

from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from app.curriculum.execution import StageFailure
from app.curriculum.local_provider import CurriculumProviderError, _json_bytes
from app.curriculum.objectives import (
    BatchExtraction, CompactExtraction, NORMALIZATION_VERSION, extract_spec,
    global_goals, normalize_extraction, parse_extraction, plan_batches,
    validate_normalized_extraction,
)
from app.curriculum.workflow import recipe_digest
from test_curriculum_contracts import context
from test_curriculum_workflow import Session


def batch_with_texts(session, texts):
    snapshot = session.context.tutorial_snapshots[0]
    template = snapshot.segments[0]
    snapshot.segments = []
    for index, text in enumerate(texts):
        item = deepcopy(template)
        item.segment_id = uuid4()
        item.text = text
        item.start_ms, item.end_ms = index * 2000, index * 2000 + 1000
        snapshot.segments.append(item)
    batches = plan_batches(session.context)
    assert len(batches) == 1
    return batches[0]


@pytest.fixture
def extraction_batch(context):
    return batch_with_texts(Session(context), [
        "Define a GET route. Return a string list.",
        "Declare the response model as list[str].",
        "This authored title card contains no instruction.",
    ])


def proposal(batch):
    return {
        "goals": [{"description": "Define a GET route.", "anchors": [
            {"slice_id": batch.slices[0].id, "quote": "Define a GET route."},
        ]}],
        "insufficient": [{"slice_id": item.id, "reason": "No additional goal selected."}
                         for item in batch.slices[1:]],
    }


def parse(batch, value):
    return parse_extraction(batch, json.dumps(value, ensure_ascii=False))


def test_compact_reply_gets_application_ids_and_complete_canonical_coverage(extraction_batch):
    batch = extraction_batch
    wire = proposal(batch)
    accepted = normalize_extraction(batch, CompactExtraction.model_validate(wire, strict=True))
    assert isinstance(accepted, BatchExtraction)
    assert [item.id for item in accepted.goals] == ["goal0"]
    assert accepted.model_dump(mode="json") == {
        "goals": [{"id": "goal0", **wire["goals"][0]}],
        "coverage": [
            {"slice_id": batch.slices[0].id, "status": "supported", "goal_ids": ["goal0"], "reason": None},
            *[{"slice_id": item["slice_id"], "status": "insufficient_evidence", "goal_ids": [],
               "reason": item["reason"]} for item in wire["insufficient"]],
        ],
    }
    assert parse(batch, wire) == accepted
    assert validate_normalized_extraction(batch, accepted) == accepted
    # The output bookkeeping is created here rather than repeated by the model.
    assert len(_json_bytes(wire)) < len(_json_bytes(accepted.model_dump(mode="json")))


def test_multiple_goals_and_shared_anchors_reconstruct_exact_coverage(extraction_batch):
    batch = extraction_batch
    first, second, third = batch.slices
    wire = {
        "goals": [
            {"description": "Declare a route and its response model.", "anchors": [
                {"slice_id": second.id, "quote": "list[str]"},
                {"slice_id": first.id, "quote": "Define a GET route."},
            ]},
            {"description": "Return a string list.", "anchors": [
                {"slice_id": first.id, "quote": "Return a string list."},
            ]},
        ],
        "insufficient": [{"slice_id": third.id, "reason": "No instruction."}],
    }
    accepted = parse(batch, wire)
    assert [item.id for item in accepted.goals] == ["goal0", "goal1"]
    assert [(item.slice_id, item.goal_ids) for item in accepted.coverage] == [
        (first.id, ["goal0", "goal1"]), (second.id, ["goal0"]), (third.id, []),
    ]
    assert accepted.goals[0].anchors[0].slice_id == second.id
    assert validate_normalized_extraction(batch, accepted) == accepted


def test_explicit_insufficiency_is_complete_and_coverage_order_is_application_owned(extraction_batch):
    batch = extraction_batch
    wire = {"goals": [], "insufficient": [
        {"slice_id": item.id, "reason": "No demonstrated technical action."}
        for item in reversed(batch.slices)
    ]}
    accepted = parse(batch, wire)
    assert accepted.goals == []
    assert [item.slice_id for item in accepted.coverage] == [item.id for item in batch.slices]
    assert all(item.status == "insufficient_evidence" and item.goal_ids == [] for item in accepted.coverage)


def test_every_slice_at_the_four_slice_bound_requires_its_own_explicit_insufficiency(context):
    batch = batch_with_texts(Session(context), [f"Authored title card {index}." for index in range(4)])
    wire = {"goals": [], "insufficient": [
        {"slice_id": item.id, "reason": "No instruction."} for item in batch.slices
    ]}
    assert len(parse(batch, wire).coverage) == 4
    for omitted in range(4):
        incomplete = deepcopy(wire)
        incomplete["insufficient"].pop(omitted)
        with pytest.raises(ValueError):
            parse(batch, incomplete)


@pytest.mark.parametrize("change", [
    "missing", "duplicate", "foreign", "overlap", "missing-all", "foreign-anchor",
    "invented-quote", "duplicate-anchor", "goal-id", "goal-foreign-field",
    "top-level-scope", "insufficient-status", "insufficient-goal-ids", "null-reason",
])
def test_incomplete_ambiguous_or_model_owned_bookkeeping_is_rejected(extraction_batch, change):
    batch = extraction_batch
    wire = proposal(batch)
    if change == "missing": wire["insufficient"].pop()
    if change == "duplicate": wire["insufficient"] = [wire["insufficient"][0]] * 2
    if change == "foreign": wire["insufficient"][-1]["slice_id"] = "s99999"
    if change == "overlap": wire["insufficient"][0]["slice_id"] = batch.slices[0].id
    if change == "missing-all": wire = {"goals": [], "insufficient": []}
    if change == "foreign-anchor": wire["goals"][0]["anchors"][0]["slice_id"] = "s99999"
    if change == "invented-quote": wire["goals"][0]["anchors"][0]["quote"] = "Unseen synthetic code."
    if change == "duplicate-anchor": wire["goals"][0]["anchors"] *= 2
    if change == "goal-id": wire["goals"][0]["id"] = "goal0"
    if change == "goal-foreign-field": wire["goals"][0]["source_id"] = str(uuid4())
    if change == "top-level-scope": wire["tenant_id"] = "foreign-tenant"
    if change == "insufficient-status": wire["insufficient"][0]["status"] = "insufficient_evidence"
    if change == "insufficient-goal-ids": wire["insufficient"][0]["goal_ids"] = []
    if change == "null-reason": wire["insufficient"][0]["reason"] = None
    with pytest.raises(ValueError):
        parse(batch, wire)


def test_repeated_goal_is_rejected_even_when_anchor_order_changes(extraction_batch):
    batch = extraction_batch
    wire = proposal(batch)
    wire["goals"][0]["anchors"].append({"slice_id": batch.slices[1].id, "quote": "list[str]"})
    wire["insufficient"] = wire["insufficient"][1:]
    repeated = deepcopy(wire["goals"][0])
    repeated["anchors"].reverse()
    wire["goals"].append(repeated)
    with pytest.raises(ValueError):
        parse(batch, wire)


@pytest.mark.parametrize("raw", [
    '{"goals":[],"goals":[],"insufficient":[]}',
    '{"goals":[],"insufficient":[{"slice_id":"s00000","slice_id":"s00001","reason":"None."}]}',
    '{"goals":[],"insufficient":NaN}',
    '{"goals":[],"insufficient":Infinity}',
    '[{"goals":[],"insufficient":[]}]',
])
def test_compact_parser_rejects_duplicate_keys_and_nonstandard_json(extraction_batch, raw):
    with pytest.raises((ValueError, CurriculumProviderError)):
        parse_extraction(extraction_batch, raw)


@pytest.mark.parametrize("field,valid,invalid", [
    ("quote", "a" * 80, "a" * 81),
    ("quote", "ş" * 40, "ş" * 40 + "a"),
    ("quote", "😀" * 20, "😀" * 20 + "a"),
    ("description", "ş" * 90, "ş" * 90 + "a"),
    ("reason", "😀" * 45, "😀" * 45 + "a"),
])
def test_compact_parser_enforces_utf8_byte_bounds(context, field, valid, invalid):
    batch = batch_with_texts(Session(context), [valid + invalid])
    if field == "reason":
        wire = {"goals": [], "insufficient": [{"slice_id": batch.slices[0].id, "reason": valid}]}
        target = wire["insufficient"][0]
    else:
        wire = {"goals": [{"description": "Define a route.", "anchors": [
            {"slice_id": batch.slices[0].id, "quote": valid if field == "quote" else "ş"},
        ]}], "insufficient": []}
        target = wire["goals"][0]["anchors"][0] if field == "quote" else wire["goals"][0]
        target[field] = valid
    accepted = parse(batch, wire)
    assert validate_normalized_extraction(batch, accepted) == accepted
    target[field] = invalid
    with pytest.raises(ValueError):
        parse(batch, wire)


@pytest.mark.parametrize("field,bad", [
    ("description", " "), ("description", "Synthetic\x00goal"),
    ("reason", " "), ("reason", "Synthetic\x00reason"),
    ("quote", " "), ("quote", "Synthetic\x00quote"),
])
def test_compact_text_cannot_be_blank_or_contain_nul(context, field, bad):
    batch = batch_with_texts(Session(context), ["Synthetic quote"])
    if field == "reason":
        wire = {"goals": [], "insufficient": [{"slice_id": batch.slices[0].id, "reason": bad}]}
    else:
        wire = {"goals": [{"description": "Synthetic goal", "anchors": [
            {"slice_id": batch.slices[0].id, "quote": "Synthetic quote"},
        ]}], "insufficient": []}
        target = wire["goals"][0]["anchors"][0] if field == "quote" else wire["goals"][0]
        target[field] = bad
    with pytest.raises((ValueError, CurriculumProviderError)):
        parse(batch, wire)


@pytest.mark.parametrize("change", ["description", "quote", "reason"])
def test_conversion_revalidates_nested_data_after_a_model_object_is_mutated(extraction_batch, change):
    batch = extraction_batch
    value = CompactExtraction.model_validate(proposal(batch), strict=True)
    if change == "description": value.goals[0].description = "ş" * 91
    if change == "quote": value.goals[0].anchors[0].quote = "Unseen synthetic code."
    if change == "reason": value.insufficient[0].reason = " "
    with pytest.raises(ValueError):
        normalize_extraction(batch, value)


def test_old_model_response_is_not_accepted_as_an_alternative_wire(extraction_batch):
    batch = extraction_batch
    canonical = parse(batch, proposal(batch))
    # This canonical contract is still valid checkpoint data, not v4 model input.
    assert BatchExtraction.model_validate_json(canonical.model_dump_json(), strict=True) == canonical
    with pytest.raises(ValueError):
        parse_extraction(batch, canonical.model_dump_json())


def test_native_schema_only_offers_actual_batch_ids_without_model_goal_identity(context):
    session = Session(context)
    batch = batch_with_texts(session, ["Define a route.", "Return a dictionary."])
    spec = extract_spec(batch, session.context.request.learner)
    assert spec.prompt_version == "tutorial-objectives-v4"
    assert spec.schema_version == "tutorial-objectives-json-v4"
    assert NORMALIZATION_VERSION == "compact-extraction-map-v1"
    definitions = spec.output_schema["$defs"]
    assert set(spec.output_schema["properties"]) == {"goals", "insufficient"}
    prepared = session.calls.provider.prepare(spec)
    # The provider sorts JSON keys. The actual serialized schema must still
    # present goals before bookkeeping; declaration order alone is insufficient.
    assert list(json.loads(prepared.payload)["format"]["properties"]) == ["goals", "insufficient"]
    assert "id" not in definitions["ProposedGoal"]["properties"]
    for name in ("GoalAnchor", "InsufficientSlice"):
        assert definitions[name]["properties"]["slice_id"]["enum"] == [item.id for item in batch.slices]
    assert "enum" not in CompactExtraction.model_json_schema()["$defs"]["GoalAnchor"]["properties"]["slice_id"]


def test_repeated_quote_across_sources_binds_only_the_named_slice_and_unicode_span(context):
    session = Session(context)
    snapshot = session.context.tutorial_snapshots[0]
    target = snapshot.segments[0]
    quote = "Define a GET route."
    target.text = "ş" * 900 + quote
    other = deepcopy(snapshot)
    other.pin.source_id = uuid4()
    other.segments[0].source_id = other.pin.source_id
    other.segments[0].segment_id = uuid4()
    other.segments[0].text = quote
    session.context.request.selected_sources.append(deepcopy(other.pin))
    session.context.tutorial_snapshots.append(other)
    batches = plan_batches(session.context)
    assert len(batches) == 1
    batch = batches[0]
    named = next(item for item in batch.slices if item.segment_id == target.segment_id and item.start_char == 900)
    accepted = parse(batch, {
        "goals": [{"description": "Define a route.", "anchors": [{"slice_id": named.id, "quote": quote}]}],
        "insufficient": [{"slice_id": item.id, "reason": "No additional goal selected."}
                         for item in batch.slices if item.id != named.id],
    })
    goal = global_goals(batches, [accepted])["g00_goal0"]
    assert goal["objective"].tutorial_segment_ids == [target.segment_id]
    assert goal["quotes"] == [{"segment_id": str(target.segment_id), "source_id": str(target.source_id),
                               "modality": "transcript", "origin": "uploaded_transcript", "quote": quote}]
    assert named.text == target.text[named.start_char:named.end_char] == quote


@pytest.mark.parametrize("tamper", ["identity", "coverage-order"])
def test_canonical_checkpoint_mapping_cannot_be_rewritten_with_a_valid_payload_hash(context, tamper):
    session = Session(context)
    batch_with_texts(session, ["Define a GET route.", "No further instruction."])
    session.advance()
    session.advance()
    before = len(session.calls.requests)
    checkpoint = session.checkpoints[-1]
    extraction = checkpoint.payload["accepted"][0]["extraction"]
    if tamper == "identity":
        old = extraction["goals"][0]["id"]
        extraction["goals"][0]["id"] = "renamed"
        for coverage in extraction["coverage"]:
            coverage["goal_ids"] = ["renamed" if item == old else item for item in coverage["goal_ids"]]
    else:
        extraction["coverage"].reverse()
    checkpoint.content_sha256 = sha256(_json_bytes(checkpoint.payload)).hexdigest()
    with pytest.raises(StageFailure) as error:
        session.advance()
    assert error.value.code == "invalid_output" and not error.value.retryable
    assert len(session.calls.requests) == before


def test_v3_recipe_cannot_adopt_v4_mapping_even_with_a_valid_checkpoint_hash(context):
    session = Session(context)
    session.advance()
    previous_recipe = "a744f11e53dc3e5b226bbe5618dc82fb7b14901ab5c72a87c7e5d0db1629bf81"
    assert recipe_digest() != previous_recipe
    checkpoint = session.checkpoints[0]
    checkpoint.payload["recipe_sha256"] = previous_recipe
    checkpoint.content_sha256 = sha256(_json_bytes(checkpoint.payload)).hexdigest()
    with pytest.raises(StageFailure) as error:
        session.advance()
    assert error.value.code == "invalid_output" and not error.value.retryable
    assert session.calls.requests == []


def test_changing_only_normalization_version_invalidates_resume_before_inference(context, monkeypatch):
    session = Session(context)
    session.advance()
    before = recipe_digest()
    monkeypatch.setattr("app.curriculum.workflow.NORMALIZATION_VERSION", "compact-extraction-map-future")
    assert recipe_digest() != before
    with pytest.raises(StageFailure) as error:
        session.advance()
    assert error.value.code == "invalid_output" and not error.value.retryable
    assert session.calls.requests == []


def test_explicit_empty_goals_stop_after_persisting_canonical_insufficiency(context):
    session = Session(context)
    session.calls.reply = lambda body: {"goals": [], "insufficient": [
        {"slice_id": item["id"], "reason": "No demonstrated technical action."}
        for item in body["slices"]
    ]}
    with pytest.raises(StageFailure) as error:
        session.finish()
    assert error.value.code == "invalid_output" and not error.value.retryable
    assert [item["stage"] for item in session.calls.requests] == ["extract"]
    extraction = session.checkpoints[-1].payload["accepted"][0]["extraction"]
    assert set(extraction) == {"goals", "coverage"} and extraction["goals"] == []
    assert extraction["coverage"][0]["status"] == "insufficient_evidence"
