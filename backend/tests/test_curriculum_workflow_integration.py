"""Authored HTTP -> real graph -> scoped SQL checkpoints and draft publication."""

import json
from uuid import uuid4

import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.execution import advance_run
from app.curriculum.model_calls import LeasedCurriculumCalls
from app.curriculum.run_contracts import RunCreate
from app.curriculum.workflow import TutorialAssignmentWorkflow, WORKFLOW_VERSION
from test_curriculum_drafts_integration import saved_context
from test_curriculum_local_provider import local_curriculum_server
from test_curriculum_model_calls_integration import retire
from test_curriculum_runs_integration import make_due, read_run, state_rows
from test_curriculum_workflow import authored_reply
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


@pytest.fixture
def graph_setup(ingestion, local_curriculum_server):
    sources, _, principal, project, actor = ingestion
    provider, state = local_curriculum_server
    context = saved_context(ingestion)
    repository = RunDeliveryRepository(sources.store)
    run = repository.create(principal.tenant_id, project.id, actor, context.id,
        RunCreate(idempotency_key="graph-run-fixture", workflow_version=WORKFLOW_VERSION))
    state["phases"] = []
    def reply(request):
        body = json.loads(request["messages"][1]["content"])
        state["phases"].append(body["stage"])
        state["content"] = json.dumps(authored_reply(body))
    state["on_chat"] = reply
    return ingestion, context, run, repository, provider, state


def step(setup):
    ing, _, run, repo, provider, _ = setup
    # A fresh graph/provider adapter per delivery proves that recovery comes
    # from scoped persisted state, not Python object memory.
    advance_run(repo, run.tenant_id, run.project_id, run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repo, provider))})
    return read_run(ing, run)


def test_accepted_graph_progress_is_reused_and_final_revision_is_bound_once(graph_setup, caplog):
    ing, context, run, repo, _, state = graph_setup
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        assert step(graph_setup).checkpoint_seq == 1 and state["phases"] == []
        assert step(graph_setup).checkpoint_seq == 2 and state["phases"] == ["extract"]
        assert step(graph_setup).checkpoint_seq == 3 and state["phases"] == ["extract", "select"]
        current = step(graph_setup)
        assert current.status == "succeeded" and current.attempt_count == 4
        assert step(graph_setup) == current
    calls = state_rows(ing, run, "curriculum_model_calls")
    assert len(calls) == 3 and all(row["status"] == "succeeded" and row["billed_usd"] == 0 for row in calls)
    assert {row["prompt_version"] for row in calls} == {"tutorial-objectives-v3", "tutorial-goal-selection-v1", "tutorial-assignment-v1"}
    assert all(row["input_sha256"] is not None and row["output_tokens"] == 35 for row in calls)
    _, _, principal, project, actor = ing
    draft = DraftRepository(repo.store).read(principal.tenant_id, project.id, actor, current.result_draft_id, 1)
    assert draft.assignment.draft.objectives[0].id == "g00_route"
    assert draft.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    assert draft.assignment.documentation_snapshots == []
    assert not state_rows(ing, run, "curriculum_run_outbox")
    assert len(state_rows(ing, run, "curriculum_run_results")) == 1
    assert "synthetic health" not in caplog.text and "Expose synthetic data" not in caplog.text


@pytest.mark.parametrize("repair", ["success", "invalid", "transport-invalid"])
def test_revision_receipts_and_terminal_failure_are_truthful(graph_setup, repair):
    ing, _, run, _, _, state = graph_setup
    original = state["on_chat"]
    def invalid(request):
        original(request)
        if state["phases"][-1] == "generate" or (repair == "invalid" and state["phases"][-1] == "revise"):
            state["content"] = '{"title":"Incomplete authored draft"}'
        if repair == "transport-invalid" and state["phases"][-1] == "generate":
            state["content"] = '{"duplicate":1,"duplicate":2}'
    state["on_chat"] = invalid
    for _ in range(5):
        current = step(graph_setup)
    assert state["phases"] == ["extract", "select", "generate", "revise"]
    assert current.status == ("failed" if repair == "invalid" else "succeeded")
    assert current.checkpoint_seq == 4
    assert len(state_rows(ing, run, "curriculum_run_results")) == (0 if repair == "invalid" else 1)
    calls = sorted(state_rows(ing, run, "curriculum_model_calls"), key=lambda row: row["created_at"])
    assert len(calls) == 4 and calls[-1]["purpose"] == "revise-assignment"
    assert calls[2]["status"] == ("failed" if repair == "transport-invalid" else "succeeded")
    assert all(row["input_tokens"] == 123 and row["output_tokens"] == 35 for row in calls)
    if repair == "invalid":
        assert current.failure_code == "invalid_output" and current.failure_count == 1


def test_transient_retry_reuses_checkpoint_and_does_not_publish_partial_output(graph_setup):
    ing, _, run, _, _, state = graph_setup
    step(graph_setup)
    step(graph_setup)
    state["status"] = 503
    failed = step(graph_setup)
    assert failed.status == "retrying" and failed.failure_count == 1 and failed.checkpoint_seq == 2
    assert len(state_rows(ing, run, "curriculum_model_calls")) == 1
    state.pop("status")
    make_due(ing, run)
    assert step(graph_setup).checkpoint_seq == 3
    assert step(graph_setup).status == "succeeded"
    assert state["phases"] == ["extract", "select", "generate"]


@pytest.mark.parametrize("boundary", ["cancelled", "expired", "archive", "revoked", "source-delete", "project-delete"])
def test_late_graph_output_never_adds_checkpoint_or_failure_after_lease_loss(graph_setup, boundary):
    ing, _, run, repo, _, state = graph_setup
    step(graph_setup)
    original = state["on_chat"]
    def withdraw(request):
        original(request)
        retire(ing, run, repo, boundary)
    state["on_chat"] = withdraw
    advance_run(repo, run.tenant_id, run.project_id, run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repo, graph_setup[4]))})
    rows = state_rows(ing, run, "curriculum_run_checkpoints")
    assert len(rows) == (0 if boundary.endswith("delete") else 1)
    assert not state_rows(ing, run, "curriculum_run_results")
    if not boundary.endswith("delete"):
        with repo.store._connect() as connection:
            assert connection.execute("SELECT failure_count FROM curriculum_runs WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                      (run.tenant_id, run.project_id, run.id)).fetchone()["failure_count"] == 0
    assert state["phases"] == ["extract"]


@pytest.mark.parametrize("boundary", ["tenant", "project", "run"])
def test_wrong_scope_does_not_start_graph_or_inference(graph_setup, boundary):
    ing, _, run, repo, provider, state = graph_setup
    advance_run(repo, "foreign-tenant" if boundary == "tenant" else run.tenant_id,
                uuid4() if boundary == "project" else run.project_id, uuid4() if boundary == "run" else run.id,
                {WORKFLOW_VERSION: TutorialAssignmentWorkflow(LeasedCurriculumCalls(repo, provider))})
    assert read_run(ing, run).attempt_count == 0 and state["calls"] == []
