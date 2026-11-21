"""The explicitly pinned Qwen2.5 candidate has isolated, resumable SQL state."""

from copy import deepcopy

import pytest

from app.curriculum.drafts import DraftRepository
from app.curriculum.execution import advance_run
from app.curriculum.local_provider import LocalModelIdentity
from test_curriculum_local_provider import local_curriculum_server
from test_curriculum_qwen35_workflow_integration import accepted, configured
from test_curriculum_runs_integration import read_run, state_rows
from test_curriculum_workflow_integration import graph_setup, step
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration
MODEL = "qwen2.5:7b-instruct-q4_K_M"


def identity(**changes):
    return LocalModelIdentity(**({"model": MODEL, "model_digest": "d" * 64,
                                 "engine": "0.40.3"} | changes))


def candidate(setup, selected):
    setup = configured(setup, selected)
    if selected.model == MODEL:
        setup[-1]["show"]["details"]["family"] = "qwen2"
    return setup


def test_qwen25_checkpoint_resumes_with_fresh_adapters_and_no_reextraction(graph_setup):
    setup = candidate(graph_setup, identity())
    ing, context, run, repository, provider, state = setup
    checkpoint = deepcopy(accepted(setup))
    assert checkpoint["payload"]["identity"] == provider.identity.model_dump(mode="json")
    ing[0].artifacts.fail_get = True
    restarted = candidate(setup, provider.identity)
    assert restarted[3] is not repository and restarted[4] is not provider
    assert step(restarted).checkpoint_seq == 3
    current = step(restarted)
    assert current.status == "succeeded"
    assert state["phases"] == ["extract", "select", "generate"]
    calls = state_rows(ing, run, "curriculum_model_calls")
    assert len(calls) == state["calls"].count("/api/chat") == 3
    assert all(row["status"] == "succeeded" and row["model"] == MODEL
               and row["model_digest"] == provider.identity.model_digest
               and row["engine"] == provider.identity.engine and row["billed_usd"] == 0 for row in calls)
    saved = DraftRepository(repository.store).read(run.tenant_id, run.project_id, ing[4], current.result_draft_id)
    assert saved.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    assert next(row for row in state_rows(ing, run, "curriculum_run_checkpoints")
                if row["stage"] == "curriculum.extracted") == checkpoint


@pytest.mark.parametrize("before,after", [
    ({"model": "qwen3:4b"}, {}),
    ({"model": "qwen3.5:4b"}, {}),
    ({}, {"model": "qwen3:4b"}),
    ({}, {"model": "qwen3.5:4b"}),
    ({}, {"model_digest": "e" * 64}),
    ({}, {"engine": "0.40.4"}),
])
def test_qwen25_model_or_runtime_change_cannot_adopt_another_identitys_state(graph_setup, before, after):
    setup = candidate(graph_setup, identity(**before))
    checkpoint = deepcopy(accepted(setup))
    ing, _, run, _, _, state = setup
    previous_io = list(state["calls"])
    current = step(candidate(setup, identity(**after)))
    assert current.status == "failed" and current.failure_code == "invalid_output"
    assert current.checkpoint_seq == 2 and current.result_draft_id is None
    assert state["calls"] == previous_io and state["phases"] == ["extract"]
    assert len(state_rows(ing, run, "curriculum_model_calls")) == 1
    assert not state_rows(ing, run, "curriculum_run_results")
    assert next(row for row in state_rows(ing, run, "curriculum_run_checkpoints")
                if row["stage"] == "curriculum.extracted") == checkpoint


def test_qwen25_saved_checkpoint_does_not_open_the_empty_registry(graph_setup):
    setup = candidate(graph_setup, identity())
    accepted(setup)
    ing, _, run, repository, _, state = setup
    previous_io = list(state["calls"])
    advance_run(repository, run.tenant_id, run.project_id, run.id, {})
    current = read_run(ing, run)
    assert current.status == "failed" and current.failure_code == "processing_unavailable"
    assert state["calls"] == previous_io and state["phases"] == ["extract"]
    assert not state_rows(ing, run, "curriculum_run_results")


def test_qwen25_wrong_response_identity_fails_without_automatic_fallback(graph_setup):
    setup = candidate(graph_setup, identity())
    ing, _, run, _, provider, state = setup
    assert step(setup).checkpoint_seq == 1
    state["override"]["model"] = "qwen3:4b"
    current = step(setup)
    assert current.status == "failed" and current.failure_code == "invalid_output"
    assert current.checkpoint_seq == 1 and current.result_draft_id is None
    assert provider.identity == identity()
    chats = [request for route, request in state["requests"] if route == "/api/chat"]
    assert len(chats) == 1 and chats[0]["model"] == MODEL
    calls = state_rows(ing, run, "curriculum_model_calls")
    assert len(calls) == 1 and calls[0]["model"] == MODEL and calls[0]["status"] == "failed"
    assert not state_rows(ing, run, "curriculum_run_results")
