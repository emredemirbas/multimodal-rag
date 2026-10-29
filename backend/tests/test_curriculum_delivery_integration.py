"""Synthetic durable-stage publication and continuation with real database fences."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.persistence import DraftReplace
from app.curriculum.run_contracts import CheckpointSave, RunCommand, RunCreate
from app.models import ProjectCreate
from app.sources.contracts import SourceError
from test_curriculum_contexts_integration import wait_for_lock
from test_curriculum_drafts_integration import content_for, saved_context
from test_curriculum_progress_integration import call_start
from test_curriculum_runs_integration import create_run, read_run, state_rows
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


@pytest.fixture
def delivery(ingestion):
    sources, _, principal, project, _ = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    repository = RunDeliveryRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    return ingestion, context, run, repository, claim


def checkpoint(sequence=1):
    return CheckpointSave(sequence=sequence, stage="synthetic-objectives-v1", payload={"copied": "PRIVATE synthetic text"})


def draft_counts(ingestion):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return [connection.execute(f"SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s",
                                   (principal.tenant_id, project.id)).fetchone()["n"] for table in
                ("curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands", "curriculum_run_results")]


def test_continue_atomically_releases_lease_preserves_budget_and_loads_detached_input(delivery, caplog):
    ing, context, run, repo, claim = delivery
    _, _, principal, project, _ = ing
    assert repo.fail(claim, "provider_timeout", retryable=True)
    with repo.store._connect() as connection:
        connection.execute("UPDATE curriculum_runs SET available_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, run.id))
    claim = repo.claim(principal.tenant_id, project.id, run.id)
    current, loaded_context, checkpoints = repo.load_input(claim)
    assert current.context_id == context.id and loaded_context == context and checkpoints == []
    loaded_context.tutorial_snapshots[0].segments[0].text = "Mutated detached input"
    assert repo.load_input(claim)[1] == context
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        assert repo.continue_with_checkpoint(claim, checkpoint())
    continued = read_run(ing, run)
    assert continued.status == "pending" and continued.lease_expires_at is None
    assert continued.failure_count == 1 and continued.checkpoint_seq == 1 and continued.attempt_count == 2
    attempts = {row["attempt_number"]: row["status"] for row in state_rows(ing, run, "curriculum_run_attempts")}
    assert attempts == {1: "failed", 2: "checkpointed"}
    assert len(state_rows(ing, run, "curriculum_run_checkpoints")) == 1
    outbox = state_rows(ing, run, "curriculum_run_outbox")[0]
    assert outbox["sent_at"] is outbox["lease_token"] is outbox["lease_expires_at"] is None
    assert repo.load_input(claim) is None and not repo.continue_with_checkpoint(claim, checkpoint(2))
    next_claim = repo.claim(principal.tenant_id, project.id, run.id)
    assert next_claim.attempt_number == 3 and next_claim.lease_token != claim.lease_token
    accepted = repo.load_input(next_claim)[2]
    assert len(accepted) == 1 and accepted[0].payload == checkpoint().payload
    assert accepted[0].attempt_number == 2 and accepted[0].workflow_version == run.workflow_version
    with pytest.raises(SourceError) as error:
        repo.continue_with_checkpoint(next_claim, checkpoint())
    assert error.value.code == "checkpoint_sequence_conflict"
    assert read_run(ing, run).status == "running"
    assert "PRIVATE" not in "\n".join(record.message for record in caplog.records)


def test_publication_commits_one_bound_draft_and_exact_revision_pointer(delivery, caplog):
    ing, context, run, repo, claim = delivery
    _, _, principal, project, actor = ing
    with caplog.at_level("INFO", logger="tutorial_workspace"), ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.publish_draft(claim, content_for(context)), range(2)))
    result = next(item for item in results if item is not None)
    assert sum(item is not None for item in results) == 1
    assert result.context_id == context.id and result.revision == 1
    assert result.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    done = read_run(ing, run)
    assert done.status == "succeeded" and done.result_draft_id == result.id and done.result_revision == 1
    assert done.finished_at is not None and done.lease_expires_at is None and done.failure_code is None
    assert state_rows(ing, run, "curriculum_run_attempts")[0]["status"] == "succeeded"
    assert not state_rows(ing, run, "curriculum_run_outbox")
    assert draft_counts(ing) == [1, 1, 0, 1]
    assert repo.publish_draft(claim, content_for(context)) is None
    assert repo.claim(principal.tenant_id, project.id, run.id) is None
    assert not repo.recover_expired(principal.tenant_id, project.id, run.id)
    assert repo.create(principal.tenant_id, project.id, actor, context.id,
                       RunCreate(idempotency_key="curriculum-run-key", workflow_version=run.workflow_version)) == done
    drafts = DraftRepository(repo.store)
    edited = drafts.replace(principal.tenant_id, project.id, actor, result.id,
                            DraftReplace(idempotency_key="edit-generated-draft", expected_revision=1,
                                         content=content_for(context, title="Edited generated draft")))
    assert edited.revision == 2 and read_run(ing, run).result_revision == 1
    assert drafts.read(principal.tenant_id, project.id, actor, result.id, 1) == result
    assert "synthetic health" not in "\n".join(record.message for record in caplog.records)
    for method in (repo.cancel, repo.retry):
        with pytest.raises(SourceError) as error:
            method(principal.tenant_id, project.id, actor, run.id, RunCommand(idempotency_key="completed-command"))
        assert error.value.code == "curriculum_run_state_conflict"


def test_deleting_generated_draft_removes_result_pointer_but_never_reopens_run(delivery):
    ing, context, run, repo, claim = delivery
    _, _, principal, project, actor = ing
    result = repo.publish_draft(claim, content_for(context))
    DraftRepository(repo.store).delete(principal.tenant_id, project.id, actor, result.id)
    current = read_run(ing, run)
    assert current.status == "succeeded" and current.result_draft_id is current.result_revision is None
    assert draft_counts(ing) == [0, 0, 0, 0]
    assert repo.claim(principal.tenant_id, project.id, run.id) is None
    assert repo.publish_draft(claim, content_for(context)) is None


@pytest.mark.parametrize("operation", ["continue", "publish"])
def test_open_calls_cannot_be_orphaned_by_a_successful_delivery(delivery, operation):
    ing, context, run, repo, claim = delivery
    assert repo.begin_call(claim, call_start())
    with pytest.raises(SourceError) as error:
        (repo.continue_with_checkpoint(claim, checkpoint()) if operation == "continue" else
         repo.publish_draft(claim, content_for(context)))
    assert error.value.code == "curriculum_calls_incomplete"
    assert read_run(ing, run).status == "running" and draft_counts(ing) == [0, 0, 0, 0]
    assert not state_rows(ing, run, "curriculum_run_checkpoints")


@pytest.mark.parametrize("changed", ["strict", "nul", "evidence", "effort", "scope"])
def test_invalid_content_leaves_no_draft_or_success(delivery, changed):
    ing, context, run, repo, claim = delivery
    content = content_for(context)
    if changed == "strict":
        content.estimated_minutes = True
    elif changed == "nul":
        content.title = "PRIVATE\x00content"
    elif changed == "evidence":
        content.objectives[0].tutorial_segment_ids = [uuid4()]
    elif changed == "effort":
        content.estimated_minutes = context.request.learner.available_minutes + 1
    else:
        content = content.model_copy(update={"tenant_id": "foreign-tenant"})
    with pytest.raises(SourceError) as error:
        repo.publish_draft(claim, content)
    assert error.value.code == "invalid_curriculum_draft"
    assert draft_counts(ing) == [0, 0, 0, 0] and read_run(ing, run).status == "running"


@pytest.mark.parametrize("operation", ["load", "continue", "publish"])
@pytest.mark.parametrize("boundary", ["token", "attempt", "foreign-project", "expired", "cancelled", "revoked", "archive", "context"])
def test_each_stage_boundary_fences_stale_or_ineligible_work(delivery, operation, boundary):
    ing, context, run, repo, claim = delivery
    sources, service, principal, project, actor = ing
    if boundary == "token":
        claim = claim.model_copy(update={"lease_token": uuid4()})
    elif boundary == "attempt":
        claim = claim.model_copy(update={"attempt_number": True})
    elif boundary == "foreign-project":
        other = service.create_project(principal, ProjectCreate(title="Other scope"))
        claim = claim.model_copy(update={"project_id": other.id})
    elif boundary == "cancelled":
        repo.cancel(principal.tenant_id, project.id, actor, run.id, RunCommand(idempotency_key="cancel-stage-output"))
    elif boundary == "archive":
        service.archive_project(principal, project.id)
    else:
        with sources.store._connect() as connection:
            if boundary == "expired":
                connection.execute("UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (principal.tenant_id, project.id, run.id))
            elif boundary == "revoked":
                connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
            else:
                connection.execute("DELETE FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, context.id))
    if operation == "load":
        assert repo.load_input(claim) is None
    elif operation == "continue":
        assert repo.continue_with_checkpoint(claim, checkpoint()) is False
    else:
        assert repo.publish_draft(claim, content_for(context)) is None
    assert draft_counts(ing) == [0, 0, 0, 0]
    assert not state_rows(ing, run, "curriculum_run_checkpoints")


@pytest.mark.parametrize("target", ["source", "context", "project"])
def test_dependency_delete_cascades_generated_text_result_and_run(delivery, target):
    ing, context, run, repo, claim = delivery
    sources, _, principal, project, _ = ing
    assert repo.publish_draft(claim, content_for(context))
    with sources.store._connect() as connection:
        if target == "source":
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.request.selected_sources[0].source_id))
        elif target == "context":
            connection.execute("DELETE FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.id))
        else:
            connection.execute("DELETE FROM projects WHERE tenant_id=%s AND id=%s", (principal.tenant_id, project.id))
    assert draft_counts(ing) == [0, 0, 0, 0]
    assert not state_rows(ing, run, "curriculum_run_attempts")
    assert repo.load_input(claim) is None


@pytest.mark.parametrize("operation", ["continue", "publish"])
def test_interrupted_final_transition_rolls_back_all_stage_output(delivery, operation):
    ing, context, run, repo, claim = delivery
    with repo.store._connect() as connection:
        connection.execute("""CREATE FUNCTION reject_delivery_transition() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Synthetic transaction interruption' USING ERRCODE='40001'; END $$""")
        connection.execute("""CREATE TRIGGER reject_delivery_transition BEFORE UPDATE OF status ON curriculum_runs
            FOR EACH ROW EXECUTE FUNCTION reject_delivery_transition()""")
    with pytest.raises(psycopg.errors.SerializationFailure):
        (repo.continue_with_checkpoint(claim, checkpoint()) if operation == "continue" else
         repo.publish_draft(claim, content_for(context)))
    assert draft_counts(ing) == [0, 0, 0, 0] and read_run(ing, run).status == "running"
    assert not state_rows(ing, run, "curriculum_run_checkpoints")
    assert state_rows(ing, run, "curriculum_run_attempts")[0]["status"] == "running"
    with repo.store._connect() as connection:
        connection.execute("DROP TRIGGER reject_delivery_transition ON curriculum_runs")
    assert (repo.continue_with_checkpoint(claim, checkpoint()) if operation == "continue" else
            repo.publish_draft(claim, content_for(context)))


@pytest.mark.parametrize("operation", ["continue", "publish"])
def test_expiry_after_project_lock_wait_prevents_output(delivery, monkeypatch, operation):
    ing, context, run, repo, claim = delivery
    sources, _, principal, project, _ = ing
    original_connect = sources.store._connect
    with original_connect() as connection:
        connection.execute("UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()+interval '0.4 seconds' WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, run.id))
    with original_connect() as blocker:
        blocker.execute("SELECT id FROM projects WHERE tenant_id=%s AND id=%s FOR UPDATE", (principal.tenant_id, project.id))
        def named_connect():
            connection = original_connect()
            connection.execute("SET application_name='curriculum-delivery-expiry-wait'")
            return connection
        monkeypatch.setattr(sources.store, "_connect", named_connect)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(repo.continue_with_checkpoint, claim, checkpoint()) if operation == "continue" else pool.submit(repo.publish_draft, claim, content_for(context))
            assert wait_for_lock(sources.store, "curriculum-delivery-expiry-wait", future)
            blocker.execute("SELECT pg_sleep(0.5)")
            blocker.commit()
            assert not future.result(timeout=5)
    assert draft_counts(ing) == [0, 0, 0, 0]
    assert not state_rows(ing, run, "curriculum_run_checkpoints")


@pytest.mark.parametrize("operation", ["continue", "publish"])
def test_expiry_during_final_outbox_write_rolls_back_all_output(delivery, operation):
    ing, context, run, repo, claim = delivery
    with repo.store._connect() as connection:
        connection.execute("""CREATE FUNCTION pause_delivery_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.5); IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
        connection.execute("""CREATE TRIGGER pause_delivery_outbox BEFORE UPDATE OR DELETE ON curriculum_run_outbox
            FOR EACH ROW EXECUTE FUNCTION pause_delivery_outbox()""")
        connection.execute("UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()+interval '0.3 seconds' "
                           "WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (claim.tenant_id, claim.project_id, claim.run_id))
    assert not (repo.continue_with_checkpoint(claim, checkpoint()) if operation == "continue" else
                repo.publish_draft(claim, content_for(context)))
    assert draft_counts(ing) == [0, 0, 0, 0] and read_run(ing, run).status == "running"
    assert not state_rows(ing, run, "curriculum_run_checkpoints")
    assert state_rows(ing, run, "curriculum_run_attempts")[0]["status"] == "running"
    assert len(state_rows(ing, run, "curriculum_run_outbox")) == 1
