"""Authored unit-selection peers exercise workflow replay, never native quality."""

from copy import deepcopy
from hashlib import sha256

import pytest

from app.curriculum.evidence_units import plan_evidence_units
from app.curriculum.execution import StageFailure
from app.curriculum.local_provider import _json_bytes
from app.curriculum.objectives import extract_spec, plan_batches
from app.curriculum import workflow as workflow_module
from test_curriculum_contracts import context
from test_curriculum_workflow import AuthoredCalls, Session, authored_reply


LEGACY_V4_RECIPE = "b0363c1d62a24aa752d388b154891af1fab0212dfc582d03edbaf99efcf1d7ca"


@pytest.fixture
def unit_session(context):
    session = Session(context)
    session.context.tutorial_snapshots[0].segments[0].text = "A" * 80 + "B" * 80
    return session


def rehash(checkpoint):
    checkpoint.content_sha256 = sha256(_json_bytes(checkpoint.payload)).hexdigest()


def extract(session):
    assert session.advance().checkpoint.stage == "curriculum.initialized"
    assert session.advance().checkpoint.stage == "curriculum.extracted"
    return session.checkpoints[-1]


def test_checkpoint_retains_full_wire_selection_and_exact_unit_plan(unit_session):
    def reply(body):
        value = authored_reply(body)
        if body["stage"] == "extract":
            value["goals"][0]["unit_ids"] = [body["slices"][0]["units"][1]["id"]]
        return value

    unit_session.calls.reply = reply
    checkpoint = extract(unit_session)
    plan = plan_evidence_units(plan_batches(unit_session.context)[0])
    accepted = checkpoint.payload["accepted"][0]
    assert accepted["unit_plan_sha256"] == plan.plan_sha256
    assert accepted["selection"] == {
        "goals": [{"description": "Define an API route.", "unit_ids": ["u00001"]}],
        "insufficient": [],
    }
    selected = plan.units[1]
    assert selected.start_char == 80 and selected.end_char == 160
    assert accepted["unit_bindings"] == [[selected.model_dump(mode="json")]]
    assert accepted["extraction"]["goals"][0]["anchors"] == [
        {"slice_id": selected.slice_id, "quote": selected.text}
    ]
    assert unit_session.finish().objectives[0].tutorial_segment_ids == [selected.segment_id]
    generation = unit_session.calls.requests[-1]
    assert generation["stage"] == "generate"
    assert generation["evidence"][0]["quotes"] == [{
        "segment_id": str(selected.segment_id), "source_id": str(selected.source_id),
        "modality": selected.modality, "origin": selected.origin, "quote": "B" * 80,
    }]


@pytest.mark.parametrize("change", [
    "foreign-unit", "different-valid-unit", "plan-digest", "canonical-quote",
    "canonical-description", "missing-selection", "missing-plan", "legacy-quote-wire",
    "same-quote-unit", "binding-source", "binding-offset", "missing-bindings",
])
def test_rehashed_forged_unit_progress_fails_before_another_call(unit_session, change):
    if change == "same-quote-unit":
        unit_session.context.tutorial_snapshots[0].segments[0].text = "A" * 160
    checkpoint = extract(unit_session)
    before = deepcopy(unit_session.calls.requests)
    accepted = checkpoint.payload["accepted"][0]
    if change == "foreign-unit":
        accepted["selection"]["goals"][0]["unit_ids"] = ["u99999"]
    if change in {"different-valid-unit", "same-quote-unit"}:
        accepted["selection"]["goals"][0]["unit_ids"] = ["u00001"]
    if change == "plan-digest":
        accepted["unit_plan_sha256"] = "b" * 64
    if change == "canonical-quote":
        # Still a valid literal in the same parent slice, but not the chosen unit.
        accepted["extraction"]["goals"][0]["anchors"][0]["quote"] = "B" * 80
    if change == "canonical-description":
        accepted["extraction"]["goals"][0]["description"] = "A different interpretation."
    if change == "missing-selection":
        accepted.pop("selection")
    if change == "missing-plan":
        accepted.pop("unit_plan_sha256")
    if change == "missing-bindings":
        accepted.pop("unit_bindings")
    if change == "binding-source":
        accepted["unit_bindings"][0][0]["processing_version"] = "another-source-version"
    if change == "binding-offset":
        accepted["unit_bindings"][0][0]["start_char"] += 1
        accepted["unit_bindings"][0][0]["end_char"] += 1
    if change == "legacy-quote-wire":
        accepted["selection"] = {
            "goals": [{"description": "Define an API route.",
                       "anchors": [{"slice_id": "s00000", "quote": "A" * 80}]}],
            "insufficient": [],
        }
    rehash(checkpoint)
    with pytest.raises(StageFailure) as failure:
        unit_session.advance()
    assert failure.value.code == "invalid_output" and not failure.value.retryable
    assert unit_session.calls.requests == before


def test_identical_quote_units_keep_selected_identity_after_process_loss(unit_session):
    unit_session.context.tutorial_snapshots[0].segments[0].text = "A" * 160

    def reply(body):
        value = authored_reply(body)
        if body["stage"] == "extract":
            value["goals"][0]["unit_ids"] = ["u00001"]
        return value

    unit_session.calls.reply = reply
    extract(unit_session)
    persisted = deepcopy(unit_session.checkpoints)
    plan = plan_evidence_units(plan_batches(unit_session.context)[0])
    assert plan.units[0].text == plan.units[1].text
    assert plan.units[0].start_char != plan.units[1].start_char
    # A fresh graph, provider boundary and request recorder stand in for the lost
    # process. Only detached persisted progress is available to this continuation.
    unit_session.calls = AuthoredCalls()
    unit_session.checkpoints = deepcopy(persisted)
    assert unit_session.finish().title == "A small authored API"
    assert [body["stage"] for body in unit_session.calls.requests] == ["select", "generate"]
    assert unit_session.checkpoints[:len(persisted)] == persisted
    for checkpoint in unit_session.checkpoints[1:]:
        accepted = checkpoint.payload["accepted"][0]
        assert accepted["selection"]["goals"][0]["unit_ids"] == ["u00001"]
        assert accepted["unit_plan_sha256"] == plan.plan_sha256
        assert accepted["unit_bindings"] == [[plan.units[1].model_dump(mode="json")]]
        assert accepted["extraction"]["goals"][0]["anchors"][0]["quote"] == "A" * 80


def test_later_checkpoint_cannot_swap_identical_quote_unit_identity(unit_session):
    unit_session.context.tutorial_snapshots[0].segments[0].text = "A" * 160
    extract(unit_session)
    assert unit_session.advance().checkpoint.stage == "curriculum.selected"
    checkpoint = unit_session.checkpoints[-1]
    before = deepcopy(unit_session.calls.requests)
    # Normalizing either unit gives the same literal anchor. Replay must still
    # reject replacing the selection accepted in the earlier checkpoint.
    checkpoint.payload["accepted"][0]["selection"]["goals"][0]["unit_ids"] = ["u00001"]
    rehash(checkpoint)
    with pytest.raises(StageFailure) as failure:
        unit_session.advance()
    assert failure.value.code == "invalid_output"
    assert unit_session.calls.requests == before


def test_old_v4_recipe_is_not_resumed_even_with_recomputed_content_hash(unit_session):
    assert workflow_module.recipe_digest() != LEGACY_V4_RECIPE
    unit_session.advance()
    checkpoint = unit_session.checkpoints[0]
    checkpoint.payload["recipe_sha256"] = LEGACY_V4_RECIPE
    rehash(checkpoint)
    with pytest.raises(StageFailure) as failure:
        unit_session.advance()
    assert failure.value.code == "invalid_output" and unit_session.calls.requests == []


@pytest.mark.parametrize("pin,value", [
    ("PARTITION_VERSION", "evidence-units-byte-v2"),
    ("MAX_UNIT_BYTES", 79),
])
def test_partition_recipe_change_rejects_existing_progress_without_calls(unit_session, monkeypatch, pin, value):
    extract(unit_session)
    before = deepcopy(unit_session.calls.requests)
    previous = workflow_module.recipe_digest()
    monkeypatch.setattr(workflow_module.evidence_units, pin, value)
    assert workflow_module.recipe_digest() != previous
    with pytest.raises(StageFailure):
        unit_session.advance()
    assert unit_session.calls.requests == before


def test_initial_plan_pins_unit_source_identity_even_when_model_request_is_identical(unit_session):
    other = Session((deepcopy(unit_session.context.request), None,
                     deepcopy(unit_session.context.tutorial_snapshots[0])))
    changed_version = "transcript-chunks-v1:g4:another-recipe"
    other.context.request.selected_sources[0].processing_version = changed_version
    other.context.tutorial_snapshots[0].pin.processing_version = changed_version
    other.context.tutorial_snapshots[0].segments[0].processing_version = changed_version
    first_batch = plan_batches(unit_session.context)[0]
    other_batch = plan_batches(other.context)[0]
    prepare = unit_session.calls.provider.prepare
    assert prepare(extract_spec(first_batch, unit_session.context.request.learner)).input_sha256 == prepare(
        extract_spec(other_batch, other.context.request.learner)).input_sha256
    assert plan_evidence_units(first_batch).plan_sha256 != plan_evidence_units(other_batch).plan_sha256
    unit_session.advance()
    other.advance()
    first, second = unit_session.checkpoints[0].payload, other.checkpoints[0].payload
    assert first["plan_sha256"] != second["plan_sha256"]
    assert first["context_sha256"] != second["context_sha256"]
