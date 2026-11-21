"""Authored Qwen3.5 HTTP uses the same scoped SQL recovery and receipt fences."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.execution import advance_run
from app.curriculum.local_provider import LocalCurriculumProvider
from app.curriculum.model_calls import LeasedCurriculumCalls
from app.curriculum.workflow import TutorialAssignmentWorkflow, WORKFLOW_VERSION
from test_curriculum_local_provider import local_curriculum_server
from test_curriculum_model_calls_integration import retire
from test_curriculum_qwen35_workflow import candidate_identity
from test_curriculum_runs_integration import read_run, state_rows
from test_curriculum_workflow_integration import graph_setup, step
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def configured(setup, identity):
    ing, context, run, repository, previous, state = setup
    state["tags"] = {"models": [{"name": identity.model, "digest": identity.model_digest}]}
    state["show"] = {"capabilities": ["completion"],
                     "details": {"family": "qwen35" if identity.model == "qwen3.5:4b" else "qwen3"}}
    state["version"] = {"version": identity.engine}
    state["override"] = {"model": identity.model}
    return (ing, context, run, RunDeliveryRepository(repository.store),
            LocalCurriculumProvider(previous.base_url, identity), state)


@pytest.fixture
def qwen35_graph(graph_setup):
    return configured(graph_setup, candidate_identity())


def accepted(setup):
    assert step(setup).checkpoint_seq == 1
    assert step(setup).checkpoint_seq == 2
    assert setup[-1]["phases"] == ["extract"]
    return next(row for row in state_rows(setup[0], setup[2], "curriculum_run_checkpoints")
                if row["stage"] == "curriculum.extracted")


def test_qwen35_accepted_extraction_resumes_with_fresh_sql_and_provider_adapters(qwen35_graph, caplog):
    ing, context, run, repository, provider, state = qwen35_graph
    checkpoint = deepcopy(accepted(qwen35_graph))
    assert checkpoint["payload"]["identity"] == provider.identity.model_dump(mode="json")
    ing[0].artifacts.fail_get = True
    restarted = configured(qwen35_graph, provider.identity)
    assert restarted[3] is not repository and restarted[4] is not provider
    assert step(restarted).checkpoint_seq == 3
    current = step(restarted)
    assert current.status == "succeeded"
    assert state["phases"] == ["extract", "select", "generate"]
    assert state["calls"].count("/api/chat") == 3
    calls = state_rows(ing, run, "curriculum_model_calls")
    assert len(calls) == 3
    assert all(row["status"] == "succeeded" and row["model"] == "qwen3.5:4b"
               and row["model_digest"] == provider.identity.model_digest
               and row["engine"] == provider.identity.engine and row["billed_usd"] == 0 for row in calls)
    assert next(row for row in calls if row["purpose"] == "extract-objectives")["input_sha256"] == (
        checkpoint["payload"]["accepted"][0]["input_sha256"])
    saved = DraftRepository(repository.store).read(run.tenant_id, run.project_id, ing[4], current.result_draft_id)
    assert saved.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    assert len(state_rows(ing, run, "curriculum_run_results")) == 1
    assert next(row for row in state_rows(ing, run, "curriculum_run_checkpoints")
                if row["stage"] == "curriculum.extracted") == checkpoint
    assert "synthetic health" not in caplog.text


@pytest.mark.parametrize("before,after", [
    ({"model": "qwen3:4b"}, {}),
    ({}, {"model": "qwen3:4b"}),
    ({}, {"model_digest": "c" * 64}),
    ({}, {"engine": "0.40.4"}),
])
def test_changed_candidate_cannot_adopt_sql_progress_or_start_provider_io(graph_setup, before, after):
    setup = configured(graph_setup, candidate_identity(**before))
    checkpoint = deepcopy(accepted(setup))
    ing, _, run, _, _, state = setup
    previous_io = list(state["calls"])
    changed = configured(setup, candidate_identity(**after))
    current = step(changed)
    assert current.status == "failed" and current.failure_code == "invalid_output"
    assert current.checkpoint_seq == 2 and current.result_draft_id is None
    assert state["calls"] == previous_io and state["phases"] == ["extract"]
    assert len(state_rows(ing, run, "curriculum_model_calls")) == 1
    assert not state_rows(ing, run, "curriculum_run_results")
    assert next(row for row in state_rows(ing, run, "curriculum_run_checkpoints")
                if row["stage"] == "curriculum.extracted") == checkpoint


@pytest.mark.parametrize("scope", ["tenant", "project"])
def test_qwen35_registry_still_requires_both_scope_components(qwen35_graph, scope):
    ing, _, run, repository, provider, state = qwen35_graph
    advance_run(repository, "foreign-tenant" if scope == "tenant" else run.tenant_id,
                uuid4() if scope == "project" else run.project_id, run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repository, provider))})
    assert read_run(ing, run).attempt_count == 0 and state["calls"] == []
    assert not state_rows(ing, run, "curriculum_model_calls")


@pytest.mark.parametrize("boundary", ["cancelled", "source-delete", "project-delete"])
def test_qwen35_saved_extraction_does_not_revive_cancelled_or_deleted_work(qwen35_graph, boundary):
    ing, _, run, repository, provider, state = qwen35_graph
    accepted(qwen35_graph)
    previous_io = list(state["calls"])
    retire(ing, run, repository, boundary)
    advance_run(repository, run.tenant_id, run.project_id, run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repository, provider))})
    assert state["calls"] == previous_io and state["phases"] == ["extract"]
    assert not state_rows(ing, run, "curriculum_run_results")
    assert len(state_rows(ing, run, "curriculum_run_checkpoints")) == (2 if boundary == "cancelled" else 0)


def test_qwen35_checkpoint_does_not_register_a_default_processor(qwen35_graph):
    ing, _, run, repository, _, state = qwen35_graph
    accepted(qwen35_graph)
    previous_io = list(state["calls"])
    advance_run(repository, run.tenant_id, run.project_id, run.id, {})
    current = read_run(ing, run)
    assert current.status == "failed" and current.failure_code == "processing_unavailable"
    assert state["calls"] == previous_io and state["phases"] == ["extract"]
    assert not state_rows(ing, run, "curriculum_run_results")
