"""Explicit authored Qwen3.5 state never adopts another model's accepted work."""

from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID

import pytest

from app.curriculum.contracts import LearnerPreferences
from app.curriculum.execution import StageFailure
from app.curriculum.local_provider import LocalCurriculumProvider, LocalModelIdentity
from app.curriculum.objectives import PromptSlice, SourceBatch, extract_spec
from app.curriculum.workflow import recipe_digest
from test_curriculum_contracts import context
from test_curriculum_workflow import AuthoredCalls, Session


LEGACY_RECIPE = "914a33be7aee39fa855aed6206905d0eca8bae47f6fd224148e4bc9d655ac5b1"


def candidate_identity(**changes):
    return LocalModelIdentity(**({"model": "qwen3.5:4b", "model_digest": "b" * 64,
                                 "engine": "0.40.3"} | changes))


def authored_calls(identity):
    calls = AuthoredCalls()
    calls.provider = LocalCurriculumProvider("http://127.0.0.1:1", identity)
    return calls


def test_legacy_native_request_and_recipe_pins_remain_identical():
    # This fixture predates the provider allowlist extension. Reconstruct its
    # complete source slices, independently of current context/batch planning.
    recorded = json.loads((Path(__file__).resolve().parents[2] /
        "docs/sprint5/native-evidence-units-results.json").read_text())
    original = LocalModelIdentity(**recorded["identity"])
    legacy = LocalCurriculumProvider("http://127.0.0.1:1", original)
    candidate = LocalCurriculumProvider("http://127.0.0.1:1", candidate_identity())
    assert recipe_digest() == recorded["recipe_sha256"] == LEGACY_RECIPE
    assert LocalModelIdentity(model_digest="a" * 64, engine="0.40.3").model == "qwen3:4b"
    for case in recorded["cases"]:
        grouped = {}
        for unit in case["unit_plan"]["units"]:
            grouped.setdefault(unit["slice_id"], []).append(unit)
        slices = []
        for slice_id, units in grouped.items():
            first, last = units[0], units[-1]
            slices.append(PromptSlice(id=slice_id, segment_id=UUID(first["segment_id"]),
                source_id=UUID(first["source_id"]), processing_version=first["processing_version"],
                modality=first["modality"], origin=first["origin"], start_char=first["start_char"],
                end_char=last["end_char"], text="".join(item["text"] for item in units)))
        spec = extract_spec(SourceBatch(index=0, slices=tuple(slices)), LearnerPreferences(**case["learner"]))
        old, new = legacy.prepare(spec), candidate.prepare(spec)
        assert old.input_sha256 == case["input_sha256"]
        assert len(old.payload) == case["request_bytes"]
        assert new.input_sha256 != old.input_sha256
        assert json.loads(new.payload) == json.loads(old.payload) | {"model": "qwen3.5:4b"}


def test_explicit_qwen35_authored_pipeline_keeps_identity_and_exact_evidence(context):
    session = Session(context)
    selected = candidate_identity()
    session.calls = authored_calls(selected)
    assert session.advance().checkpoint.stage == "curriculum.initialized"
    assert session.advance().checkpoint.stage == "curriculum.extracted"
    persisted = deepcopy(session.checkpoints)
    # Replace both adapters after acceptance; only detached saved state remains.
    session.calls = authored_calls(selected)
    result = session.finish()
    assert [body["stage"] for body in session.calls.requests] == ["select", "generate"]
    assert session.checkpoints[:2] == persisted
    assert result.objectives[0].tutorial_segment_ids == [context[2].segments[0].segment_id]
    for checkpoint in session.checkpoints:
        assert checkpoint.payload["identity"] == selected.model_dump(mode="json")
        assert checkpoint.payload["recipe_sha256"] == LEGACY_RECIPE


@pytest.mark.parametrize("before,after", [
    ({"model": "qwen3:4b"}, {}),
    ({}, {"model": "qwen3:4b"}),
    ({}, {"model_digest": "c" * 64}),
    ({}, {"engine": "0.40.4"}),
])
def test_model_digest_or_engine_change_rejects_accepted_state_before_another_call(context, before, after):
    session = Session(context)
    session.calls = authored_calls(candidate_identity(**before))
    session.advance()
    session.advance()
    persisted = deepcopy(session.checkpoints)
    session.calls = authored_calls(candidate_identity(**after))
    with pytest.raises(StageFailure) as failure:
        session.advance()
    assert failure.value.code == "invalid_output" and not failure.value.retryable
    assert session.calls.requests == [] and session.checkpoints == persisted


@pytest.mark.parametrize("flag", ["allow_prerequisites", "allow_extensions", "allow_external_documentation"])
def test_explicit_qwen35_does_not_open_external_generation(context, flag):
    session = Session(context)
    session.calls = authored_calls(candidate_identity())
    setattr(session.context.request.learner, flag, True)
    with pytest.raises(StageFailure) as failure:
        session.advance()
    assert failure.value.code == "processing_unavailable"
    assert session.calls.requests == [] and session.checkpoints == []


def test_explicit_qwen35_failure_has_no_automatic_model_fallback(context):
    session = Session(context)
    selected = candidate_identity()
    session.calls = authored_calls(selected)
    session.advance()
    session.calls.failure = StageFailure("provider_unavailable", retryable=False)
    with pytest.raises(StageFailure) as failure:
        session.advance()
    assert failure.value.code == "provider_unavailable"
    assert session.calls.provider.identity == selected
    assert len(session.calls.requests) == 1
    assert len(session.checkpoints) == 1 and session.checkpoints[0].payload["accepted"] == []
