"""Synthetic unit selections survive SQL recovery without adapting stale evidence."""

from copy import deepcopy
from hashlib import sha256
import json

from psycopg.types.json import Jsonb
import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.evidence_units import plan_evidence_units
from app.curriculum.execution import advance_run
from app.curriculum.local_provider import LocalCurriculumProvider, _json_bytes
from app.curriculum.model_calls import LeasedCurriculumCalls
from app.curriculum.objectives import plan_batches
from app.curriculum.persistence import ContextCreate, SourceSelection
from app.curriculum.repository import ContextRepository
from app.curriculum.run_contracts import RunCreate
from app.curriculum.workflow import TutorialAssignmentWorkflow, WORKFLOW_VERSION
from test_curriculum_contexts_integration import preferences
from test_curriculum_drafts_integration import saved_context
from test_curriculum_local_provider import local_curriculum_server
from test_curriculum_model_calls_integration import retire
from test_curriculum_runs_integration import state_rows
from test_curriculum_workflow import authored_reply
from test_curriculum_workflow_integration import step
from test_ingestion_integration import ingestion, register, run as index_source
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration
OLD_V4_RECIPE = "b0363c1d62a24aa752d388b154891af1fab0212dfc582d03edbaf99efcf1d7ca"


@pytest.fixture
def unit_graph_setup(ingestion, local_curriculum_server, request):
    sources, _, principal, project, actor = ingestion
    provider, state = local_curriculum_server
    # Two separate source segments supply two valid unit IDs. The authored peer
    # supports only the first parent and explicitly abstains on the second.
    if getattr(request, "param", None) == "repeated":
        piece = "A route returns synthetic health data. ".ljust(80, "x")
        queued = register(ingestion, key="repeated-unit-source",
            content=("WEBVTT\n\n00:01.000 --> 00:05.000\n" + piece * 2 + "\n").encode())
        assert index_source(sources, queued)
        source = sources.get_source(principal.tenant_id, project.id, queued.source.id)
        context = ContextRepository(sources.store).create(principal.tenant_id, project.id, actor,
            ContextCreate(idempotency_key="repeated-unit-context", learner=preferences(), selected_sources=[
                SourceSelection(source_id=source.id, generation=source.active_generation,
                                processing_version=source.processing_version)]))
    else:
        context = saved_context(ingestion, key="unit-selection-context", multiple=True)
    repository = RunDeliveryRepository(sources.store)
    run = repository.create(principal.tenant_id, project.id, actor, context.id,
        RunCreate(idempotency_key="unit-selection-run", workflow_version=WORKFLOW_VERSION))
    state["phases"] = []

    def reply(request):
        body = json.loads(request["messages"][1]["content"])
        state["phases"].append(body["stage"])
        state["content"] = json.dumps(authored_reply(body))

    state["on_chat"] = reply
    return ingestion, context, run, repository, provider, state


def accepted_checkpoint(setup):
    assert step(setup).checkpoint_seq == 1
    assert step(setup).checkpoint_seq == 2
    ing, _, run, _, _, state = setup
    assert state["phases"] == ["extract"]
    rows = state_rows(ing, run, "curriculum_run_checkpoints")
    return next(row for row in rows if row["stage"] == "curriculum.extracted")


def save_changed_checkpoint(setup, checkpoint, payload):
    ing, _, run, _, _, _ = setup
    with ing[0].store._connect() as connection:
        connection.execute(
            "UPDATE curriculum_run_checkpoints SET payload=%s,content_sha256=%s "
            "WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND sequence=%s",
            (Jsonb(payload), sha256(_json_bytes(payload)).hexdigest(),
             run.tenant_id, run.project_id, run.id, checkpoint["sequence"]),
        )


def test_persisted_unit_selection_restarts_with_exact_whole_unit_quotes_without_reextracting(unit_graph_setup):
    ing, context, run, repository, provider, state = unit_graph_setup
    checkpoint = accepted_checkpoint(unit_graph_setup)
    batches = plan_batches(context)
    plan = plan_evidence_units(batches[0])
    accepted = checkpoint["payload"]["accepted"][0]
    assert accepted["unit_plan_sha256"] == plan.plan_sha256
    assert accepted["selection"]["goals"][0]["unit_ids"] == [plan.units[0].id]
    assert accepted["unit_bindings"] == [[plan.units[0].model_dump(mode="json")]]
    anchor = accepted["extraction"]["goals"][0]["anchors"][0]
    assert anchor == {"slice_id": plan.units[0].slice_id, "quote": plan.units[0].text}
    assert "unit_ids" not in accepted["extraction"]["goals"][0]
    assert state["calls"].count("/api/chat") == 1
    assert next(row for row in state_rows(ing, run, "curriculum_model_calls")
                if row["purpose"] == "extract-objectives")["input_sha256"] == accepted["input_sha256"]
    # Reconstruct both application adapters after the accepted SQL checkpoint.
    # No artifact read is necessary to resume its immutable context and units.
    ing[0].artifacts.fail_get = True
    restarted = (ing, context, run, RunDeliveryRepository(repository.store),
                 LocalCurriculumProvider(provider.base_url, provider.identity), state)
    assert step(restarted).checkpoint_seq == 3
    current = step(restarted)
    assert current.status == "succeeded" and state["phases"] == ["extract", "select", "generate"]
    assert state["calls"].count("/api/chat") == 3
    assert len(state_rows(ing, run, "curriculum_run_results")) == 1
    sources, _, principal, project, actor = ing
    saved = DraftRepository(sources.store).read(principal.tenant_id, project.id, actor, current.result_draft_id)
    assert saved.assignment.draft.objectives[0].tutorial_segment_ids == [plan.units[0].segment_id]
    assert [item.segment_id for item in saved.assignment.tutorial_evidence] == [plan.units[0].segment_id]
    before = deepcopy(checkpoint["payload"])
    after = next(row for row in state_rows(ing, run, "curriculum_run_checkpoints")
                 if row["stage"] == "curriculum.extracted")
    assert after["payload"] == before


@pytest.mark.parametrize("change", [
    "foreign-unit", "different-valid-selection", "quote-prefix", "description-mismatch",
    "plan-digest", "unit-bindings", "missing-selection", "old-v4-wire", "old-v4-recipe",
])
def test_rehashed_checkpoint_tampering_stops_before_any_further_provider_io(unit_graph_setup, change, caplog):
    ing, context, run, _, _, state = unit_graph_setup
    checkpoint = accepted_checkpoint(unit_graph_setup)
    payload = deepcopy(checkpoint["payload"])
    accepted = payload["accepted"][0]
    plan = plan_evidence_units(plan_batches(context)[0])
    if change == "foreign-unit":
        accepted["selection"]["goals"][0]["unit_ids"] = ["u99999"]
    elif change == "different-valid-selection":
        # Both IDs exist and the substituted wire still has complete coverage;
        # the old normalized anchor may not silently stand for this selection.
        accepted["selection"]["goals"][0]["unit_ids"] = [plan.units[1].id]
        accepted["selection"]["insufficient"] = [
            {"slice_id": plan.units[0].slice_id, "reason": "A different authored selection."}]
    elif change == "quote-prefix":
        accepted["extraction"]["goals"][0]["anchors"][0]["quote"] = plan.units[0].text[:10]
    elif change == "description-mismatch":
        accepted["extraction"]["goals"][0]["description"] = "PRIVATE forged interpretation."
    elif change == "plan-digest":
        accepted["unit_plan_sha256"] = "0" * 64
    elif change == "unit-bindings":
        accepted["unit_bindings"][0][0] = plan.units[1].model_dump(mode="json")
    elif change == "missing-selection":
        del accepted["selection"]
        del accepted["unit_plan_sha256"]
    elif change == "old-v4-wire":
        goal = accepted["selection"]["goals"][0]
        del goal["unit_ids"]
        goal["anchors"] = accepted["extraction"]["goals"][0]["anchors"]
    else:
        # Even an otherwise intact checkpoint sequence cannot adopt a new recipe
        # when its old graph version string is unchanged.
        for row in state_rows(ing, run, "curriculum_run_checkpoints"):
            old_payload = deepcopy(row["payload"])
            old_payload["recipe_sha256"] = OLD_V4_RECIPE
            save_changed_checkpoint(unit_graph_setup, row, old_payload)
        payload["recipe_sha256"] = OLD_V4_RECIPE
    save_changed_checkpoint(unit_graph_setup, checkpoint, payload)
    before = list(state["calls"])
    with caplog.at_level("INFO", logger="tutorial_workspace.jobs"):
        current = step(unit_graph_setup)
    assert current.status == "failed" and current.failure_code == "invalid_output"
    assert current.checkpoint_seq == 2 and current.result_draft_id is None
    assert state["calls"] == before and state["phases"] == ["extract"]
    assert len(state_rows(ing, run, "curriculum_model_calls")) == 1
    assert not state_rows(ing, run, "curriculum_run_results")
    assert "PRIVATE forged" not in caplog.text and plan.units[0].text not in caplog.text


@pytest.mark.parametrize("unit_graph_setup", ["repeated"], indirect=True)
def test_rehashed_selection_cannot_substitute_identical_text_at_another_source_offset(unit_graph_setup):
    ing, context, run, _, _, state = unit_graph_setup
    checkpoint = accepted_checkpoint(unit_graph_setup)
    plan = plan_evidence_units(plan_batches(context)[0])
    assert len(plan.units) == 2 and plan.units[0].text == plan.units[1].text
    assert plan.units[0].slice_id == plan.units[1].slice_id
    assert plan.units[0].start_char != plan.units[1].start_char
    payload = deepcopy(checkpoint["payload"])
    accepted = payload["accepted"][0]
    assert accepted["unit_bindings"] == [[plan.units[0].model_dump(mode="json")]]
    # Canonical slice+quote bytes are identical for either occurrence. Retained
    # IDs/spans must still bind the response to the originally accepted unit.
    accepted["selection"]["goals"][0]["unit_ids"] = [plan.units[1].id]
    save_changed_checkpoint(unit_graph_setup, checkpoint, payload)
    before = list(state["calls"])
    current = step(unit_graph_setup)
    assert current.status == "failed" and current.failure_code == "invalid_output"
    assert current.checkpoint_seq == 2 and current.result_draft_id is None
    assert state["calls"] == before and state["phases"] == ["extract"]
    assert len(state_rows(ing, run, "curriculum_model_calls")) == 1
    assert not state_rows(ing, run, "curriculum_run_results")


@pytest.mark.parametrize("boundary", ["cancelled", "source-delete", "context-delete", "project-delete"])
def test_accepted_unit_selection_never_revives_cancelled_or_deleted_context(unit_graph_setup, boundary):
    ing, context, run, repository, _, state = unit_graph_setup
    accepted_checkpoint(unit_graph_setup)
    before = list(state["calls"])
    if boundary == "context-delete":
        ContextRepository(repository.store).delete(run.tenant_id, run.project_id, ing[4], context.id)
    else:
        retire(ing, run, repository, boundary)
    # A stale queued delivery cannot start selection after cancellation/deletion.
    advance_run(repository, run.tenant_id, run.project_id, run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repository, unit_graph_setup[4]))})
    assert state["calls"] == before and state["phases"] == ["extract"]
    assert not state_rows(ing, run, "curriculum_run_results")
    checkpoints = state_rows(ing, run, "curriculum_run_checkpoints")
    assert len(checkpoints) == (2 if boundary == "cancelled" else 0)
