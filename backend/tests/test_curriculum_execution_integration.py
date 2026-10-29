"""Test-only stage adapters exercise admission, bounded work and failure recovery."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.execution import StageFailure, StageResult, advance_run
from app.curriculum.run_contracts import CheckpointSave, RunCommand
from test_curriculum_drafts_integration import content_for, saved_context
from test_curriculum_progress_integration import call_start
from test_curriculum_runs_integration import create_run, make_due, read_run, state_rows
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def test_missing_processor_is_terminal_and_never_manufactures_a_draft(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunDeliveryRepository(sources.store)
    advance_run(repository, principal.tenant_id, project.id, run.id, {})
    current = read_run(ingestion, run)
    assert current.status == "failed" and current.failure_code == "processing_unavailable"
    assert current.result_draft_id is None and not state_rows(ingestion, run, "curriculum_run_outbox")
    with sources.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_drafts").fetchone()["n"] == 0


def test_one_stage_per_delivery_then_resume_and_publish_exactly_once(ingestion):
    sources, _, principal, project, _ = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    repository = RunDeliveryRepository(sources.store)
    stages = []

    def processor(stage):
        stages.append(stage.run.checkpoint_seq)
        if not stage.checkpoints:
            return StageResult(checkpoint=CheckpointSave(sequence=1, stage="fixture-prepared", payload={"prepared": True}))
        return StageResult(content=content_for(stage.context))

    processors = {run.workflow_version: processor}
    advance_run(repository, principal.tenant_id, project.id, run.id, processors)
    assert stages == [0] and read_run(ingestion, run).status == "pending"
    advance_run(repository, principal.tenant_id, project.id, run.id, processors)
    assert stages == [0, 1] and read_run(ingestion, run).status == "succeeded"
    advance_run(repository, principal.tenant_id, project.id, run.id, processors)
    assert stages == [0, 1]
    assert read_run(ingestion, run).attempt_count == 2 and read_run(ingestion, run).failure_count == 0


@pytest.mark.parametrize("boundary", ["cancel", "source-delete"])
def test_processor_holds_no_database_locks_and_late_output_cannot_restore_work(ingestion, boundary):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    repository = RunDeliveryRepository(sources.store)
    entered, release = Event(), Event()

    def processor(stage):
        entered.set()
        assert release.wait(10)
        return StageResult(content=content_for(stage.context))

    def retire():
        if boundary == "cancel":
            repository.cancel(principal.tenant_id, project.id, actor, run.id,
                              RunCommand(idempotency_key="cancel-paused-stage"))
        else:
            with sources.store._connect() as connection:
                connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (principal.tenant_id, project.id, context.request.selected_sources[0].source_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(advance_run, repository, principal.tenant_id, project.id, run.id, {run.workflow_version: processor})
        try:
            assert entered.wait(5)
            pool.submit(retire).result(timeout=5)
        finally:
            release.set()
        future.result(timeout=5)
    with sources.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_drafts").fetchone()["n"] == 0
    if boundary == "cancel":
        assert read_run(ingestion, run).status == "cancelled"
    else:
        assert repository.claim(principal.tenant_id, project.id, run.id) is None


@pytest.mark.parametrize("failure", ["adapter", "unexpected", "invalid-output"])
def test_failure_budget_interrupts_open_calls_without_leaking_private_text(ingestion, failure, caplog):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunDeliveryRepository(sources.store)

    def processor(stage):
        if failure == "invalid-output":
            content = content_for(stage.context)
            content.estimated_minutes = True
            return StageResult(content=content)
        assert repository.begin_call(stage.claim, call_start())
        if failure == "adapter":
            raise StageFailure("provider_timeout", retryable=True)
        raise RuntimeError("PRIVATE source and credentials must not reach logs")

    for count in range(1, 4):
        # Each physical attempt uses a fresh call identity from call_start().
        advance_run(repository, principal.tenant_id, project.id, run.id, {run.workflow_version: processor})
        current = read_run(ingestion, run)
        assert current.failure_count == count
        assert current.status == ("failed" if count == 3 else "retrying")
        if count < 3:
            make_due(ingestion, run)
    expected = {"adapter": "provider_timeout", "unexpected": "processing_unavailable", "invalid-output": "invalid_output"}
    assert current.failure_code == expected[failure] and current.result_draft_id is None
    calls = state_rows(ingestion, run, "curriculum_model_calls")
    assert len(calls) == (0 if failure == "invalid-output" else 3)
    assert all(row["status"] == "interrupted" and row["output_tokens"] is None for row in calls)
    assert "PRIVATE source" not in caplog.text
