"""Synthetic PostgreSQL lifecycle checks; no broker or model is invoked."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from app.curriculum.run_contracts import RunClaim, RunCommand, RunCreate
from app.curriculum.runs import RunRepository
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_curriculum_contexts_integration import wait_for_lock
from test_curriculum_drafts_integration import saved_context
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def create_run(ingestion, *, key="curriculum-run-key", context=None, workflow="curriculum-workflow-v1"):
    sources, _, principal, project, actor = ingestion
    context = context or saved_context(ingestion)
    repository = RunRepository(sources.store)
    return repository.create(principal.tenant_id, project.id, actor, context.id,
                             RunCreate(idempotency_key=key, workflow_version=workflow))


def read_run(ingestion, run):
    sources, _, principal, project, actor = ingestion
    return RunRepository(sources.store).read(principal.tenant_id, project.id, actor, run.id)


def make_due(ingestion, run, *, expired=False):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        connection.execute(
            "UPDATE curriculum_runs SET " +
            ("lease_expires_at=clock_timestamp()-interval '1 second'" if expired else
             "available_at=clock_timestamp()-interval '1 second'") +
            " WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, run.id),
        )


def state_rows(ingestion, run, table):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return connection.execute(
            f"SELECT * FROM {table} WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
            (principal.tenant_id, project.id, run.id),
        ).fetchall()


def test_create_replay_conflicts_concurrency_and_safe_logs(ingestion, caplog):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = RunRepository(sources.store)
    body = RunCreate(idempotency_key="concurrent-run-key", workflow_version="curriculum-workflow-v1")
    with caplog.at_level("INFO", logger="tutorial_workspace"), ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repository.create(principal.tenant_id, project.id, actor, context.id, body), range(2)))
    assert results[0] == results[1]
    result = results[0]
    assert result.status == "pending" and result.attempt_count == result.failure_count == result.checkpoint_seq == 0
    assert result.actor_user_id == actor and result.context_id == context.id
    assert len(state_rows(ingestion, result, "curriculum_run_outbox")) == 1
    assert state_rows(ingestion, result, "curriculum_run_attempts") == []
    with pytest.raises(SourceError) as error:
        repository.create(principal.tenant_id, project.id, actor, context.id,
                          RunCreate(idempotency_key=body.idempotency_key, workflow_version="changed-workflow-v1"))
    assert error.value.code == "idempotency_conflict"
    other = saved_context(ingestion, key="other-run-context")
    with pytest.raises(SourceError) as error:
        repository.create(principal.tenant_id, project.id, actor, other.id, body)
    assert error.value.code == "idempotency_conflict"
    events = [record.message for record in caplog.records if "curriculum_run_created" in record.message]
    assert len(events) == 1 and "attempt_count" in events[0]
    assert "concurrent-run-key" not in events[0] and "create_app" not in events[0]
    with sources.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_runs").fetchone()["n"] == 1


def test_competing_claims_have_one_fresh_token_and_no_duplicate_attempt(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: repository.claim(principal.tenant_id, project.id, run.id), range(2)))
    claim = next(value for value in claims if value is not None)
    assert sum(value is not None for value in claims) == 1
    assert claim.attempt_number == 1
    assert read_run(ingestion, run).status == "running"
    attempts = state_rows(ingestion, run, "curriculum_run_attempts")
    assert len(attempts) == 1 and attempts[0]["lease_token"] == claim.lease_token
    before = read_run(ingestion, run)
    assert repository.heartbeat(claim)
    assert read_run(ingestion, run).lease_expires_at >= before.lease_expires_at


@pytest.mark.parametrize("changed", ["tenant", "project", "run", "token", "attempt", "constructed", "mutated"])
def test_forged_and_mutated_claim_cannot_advance_or_fail_run(ingestion, changed):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    fields = claim.model_dump()
    changes = {"tenant": {"tenant_id": "foreign-tenant"}, "project": {"project_id": uuid4()},
               "run": {"run_id": uuid4()}, "token": {"lease_token": uuid4()},
               "attempt": {"attempt_number": 2}}
    if changed == "constructed":
        forged = RunClaim.model_construct(**(fields | {"attempt_number": "1"}))
    elif changed == "mutated":
        forged = RunClaim(**fields)
        forged.attempt_number = True
    else:
        forged = RunClaim(**(fields | changes[changed]))
    before = read_run(ingestion, run)
    assert not repository.heartbeat(forged)
    assert not repository.fail(forged, "provider_unavailable", retryable=True)
    assert read_run(ingestion, run) == before
    assert repository.heartbeat(claim)


def test_automatic_failure_budget_rotation_and_explicit_retry(ingestion):
    sources, _, principal, project, actor = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    previous = None
    for number in range(1, 4):
        claim = repository.claim(principal.tenant_id, project.id, run.id)
        assert claim.attempt_number == number
        if previous is not None:
            assert claim.lease_token != previous.lease_token
            assert not repository.heartbeat(previous)
        assert repository.fail(claim, "provider_timeout", retryable=True)
        assert not repository.fail(claim, "provider_timeout", retryable=True)
        current = read_run(ingestion, run)
        assert current.failure_count == number
        assert current.status == ("retrying" if number < 3 else "failed")
        if number < 3:
            outbox = state_rows(ingestion, run, "curriculum_run_outbox")
            assert len(outbox) == 1 and outbox[0]["available_at"] == current.available_at
            assert outbox[0]["lease_token"] is None and outbox[0]["sent_at"] is None
            assert repository.claim(principal.tenant_id, project.id, run.id) is None
            make_due(ingestion, run)
        previous = claim
    assert len(state_rows(ingestion, run, "curriculum_run_attempts")) == 3
    assert state_rows(ingestion, run, "curriculum_run_outbox") == []
    assert repository.claim(principal.tenant_id, project.id, run.id) is None
    retried = repository.retry(principal.tenant_id, project.id, actor, run.id,
                               RunCommand(idempotency_key="retry-after-exhaustion"))
    assert retried.status == "pending" and retried.failure_count == 0 and retried.attempt_count == 3
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    assert claim.attempt_number == 4 and claim.lease_token != previous.lease_token


def test_nonretryable_failure_and_unknown_failure_code_are_safe(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    with pytest.raises(SourceError) as error:
        repository.fail(claim, "a raw exception with secret", retryable=True)
    assert error.value.code == "invalid_curriculum_run" and "secret" not in str(error.value)
    with pytest.raises(SourceError):
        repository.fail(claim, "provider_timeout", retryable="true")
    assert repository.fail(claim, "invalid_output", retryable=False)
    current = read_run(ingestion, run)
    assert current.status == "failed" and current.failure_count == 1
    assert current.finished_at is not None and current.lease_expires_at is None


def test_expired_lease_requires_recovery_and_recovery_is_once(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    assert not repository.recover_expired(principal.tenant_id, project.id, run.id)
    make_due(ingestion, run, expired=True)
    assert not repository.heartbeat(claim)
    assert not repository.fail(claim, "provider_timeout", retryable=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        recovered = list(pool.map(lambda _: repository.recover_expired(principal.tenant_id, project.id, run.id), range(2)))
    assert sorted(recovered) == [False, True]
    current = read_run(ingestion, run)
    assert current.status == "retrying" and current.failure_code == "worker_lost" and current.failure_count == 1
    attempt = state_rows(ingestion, run, "curriculum_run_attempts")[0]
    assert attempt["status"] == "failed" and attempt["failure_code"] == "worker_lost"
    assert attempt["finished_at"] is not None


@pytest.mark.parametrize("status", ["pending", "running", "retrying"])
def test_cancel_invalidates_lease_and_replays_accepted_snapshot_after_retry(ingestion, status):
    sources, _, principal, project, actor = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = None
    if status != "pending":
        claim = repository.claim(principal.tenant_id, project.id, run.id)
        if status == "retrying":
            assert repository.fail(claim, "provider_timeout", retryable=True)
    body = RunCommand(idempotency_key="cancel-run-command")
    cancelled = repository.cancel(principal.tenant_id, project.id, actor, run.id, body)
    assert cancelled.status == "cancelled" and cancelled.failure_code == "cancelled"
    assert cancelled.lease_expires_at is None
    assert state_rows(ingestion, run, "curriculum_run_outbox") == []
    assert repository.claim(principal.tenant_id, project.id, run.id) is None
    if claim is not None:
        assert not repository.heartbeat(claim)
    retry_body = RunCommand(idempotency_key="retry-run-command")
    pending = repository.retry(principal.tenant_id, project.id, actor, run.id, retry_body)
    assert repository.cancel(principal.tenant_id, project.id, actor, run.id, body) == cancelled
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    assert claim is not None
    assert repository.retry(principal.tenant_id, project.id, actor, run.id, retry_body) == pending
    assert read_run(ingestion, run).status == "running"
    with pytest.raises(SourceError) as error:
        repository.retry(principal.tenant_id, project.id, actor, run.id, body)
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(SourceError) as error:
        repository.retry(principal.tenant_id, project.id, actor, run.id, RunCommand(idempotency_key="new-retry-key"))
    assert error.value.code == "curriculum_run_state_conflict"


def test_archive_read_replay_cancel_and_worker_fences(ingestion):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    other = create_run(ingestion, key="unclaimed-archive-run", context=context)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    cancelled = repository.cancel(principal.tenant_id, project.id, actor, other.id,
                                 RunCommand(idempotency_key="before-archive-cancel"))
    service.archive_project(principal, project.id)
    assert repository.read(principal.tenant_id, project.id, actor, run.id).status == "running"
    assert create_run(ingestion, context=context) == read_run(ingestion, run)
    assert repository.cancel(principal.tenant_id, project.id, actor, other.id,
                             RunCommand(idempotency_key="before-archive-cancel")) == cancelled
    with pytest.raises(SourceError) as error:
        create_run(ingestion, key="new-archived-run", context=context)
    assert error.value.code == "project_archived"
    with pytest.raises(SourceError) as error:
        repository.retry(principal.tenant_id, project.id, actor, other.id, RunCommand(idempotency_key="archived-retry-key"))
    assert error.value.code == "project_archived"
    assert not repository.heartbeat(claim)
    current = read_run(ingestion, run)
    assert current.status == "failed" and current.failure_code == "project_archived"
    assert state_rows(ingestion, run, "curriculum_run_outbox") == []


@pytest.mark.parametrize("stage", ["pending", "running", "expired"])
def test_revoked_original_actor_cannot_run_and_recovery_does_not_orphan_work(ingestion, stage):
    sources, _, principal, project, actor = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id) if stage != "pending" else None
    if stage == "expired":
        make_due(ingestion, run, expired=True)
    with sources.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    if stage == "pending":
        assert repository.claim(principal.tenant_id, project.id, run.id) is None
    elif stage == "running":
        assert not repository.heartbeat(claim)
    else:
        assert repository.recover_expired(principal.tenant_id, project.id, run.id)
    with sources.store._connect() as connection:
        row = connection.execute("SELECT * FROM curriculum_runs WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                 (principal.tenant_id, project.id, run.id)).fetchone()
    assert row["status"] == "failed" and row["failure_code"] == "authorization_revoked"
    assert row["lease_token"] is None and row["finished_at"] is not None
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, run.id)


def test_scopes_membership_and_retry_original_actor(ingestion):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    repository = RunRepository(sources.store)
    other_project = service.create_project(principal, ProjectCreate(title="Other project"))
    stranger = AuthenticatedPrincipal(provider="test", subject="other-run-user", tenant_id=principal.tenant_id)
    other_actor = sources.store.bootstrap_principal(stranger)
    for tenant, project_id, user in [("foreign-tenant", project.id, actor),
                                     (principal.tenant_id, other_project.id, actor),
                                     (principal.tenant_id, project.id, uuid4())]:
        with pytest.raises(ProjectNotFoundError):
            repository.read(tenant, project_id, user, run.id)
        with pytest.raises(ProjectNotFoundError):
            repository.cancel(tenant, project_id, user, run.id, RunCommand(idempotency_key="foreign-cancel-key"))
        with pytest.raises(ProjectNotFoundError):
            repository.create(tenant, project_id, user, context.id,
                              RunCreate(idempotency_key="foreign-create-key", workflow_version="workflow-v1"))
    assert repository.claim("foreign-tenant", project.id, run.id) is None
    assert repository.claim(principal.tenant_id, other_project.id, run.id) is None
    assert repository.recover_expired("foreign-tenant", project.id, run.id) is False
    cancelled = repository.cancel(principal.tenant_id, project.id, other_actor, run.id,
                                 RunCommand(idempotency_key="member-cancel-key"))
    assert cancelled.status == "cancelled"
    with pytest.raises(ProjectNotFoundError):
        repository.retry(principal.tenant_id, project.id, other_actor, run.id,
                         RunCommand(idempotency_key="member-retry-key"))


@pytest.mark.parametrize("invalid", ["constructed", "mutated"])
def test_invalid_creation_and_command_inputs_leave_no_partial_records(ingestion, invalid):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = RunRepository(sources.store)
    body = RunCreate(idempotency_key="invalid-create-key", workflow_version="workflow-v1")
    if invalid == "constructed":
        body = RunCreate.model_construct(idempotency_key=body.idempotency_key, workflow_version="bad\x00version")
    else:
        body.workflow_version = 123
    with pytest.raises(SourceError) as error:
        repository.create(principal.tenant_id, project.id, actor, context.id, body)
    assert error.value.code == "invalid_curriculum_run"
    run = create_run(ingestion, context=context)
    bad_command = RunCommand.model_construct(idempotency_key=123)
    with pytest.raises(SourceError):
        repository.cancel(principal.tenant_id, project.id, actor, run.id, bad_command)
    assert read_run(ingestion, run).status == "pending"
    assert state_rows(ingestion, run, "curriculum_run_commands") == []


def test_heartbeat_does_not_resurrect_lease_expiring_during_project_lock_wait(ingestion, monkeypatch):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    original_connect = sources.store._connect
    with original_connect() as blocker:
        blocker.execute("UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()+interval '0.5 seconds' "
                        "WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, run.id))
    with original_connect() as blocker:
        blocker.execute("SELECT id FROM projects WHERE tenant_id=%s AND id=%s FOR UPDATE", (principal.tenant_id, project.id))
        def named_connect():
            connection = original_connect()
            connection.execute("SET application_name='curriculum-expiry-wait'")
            return connection
        monkeypatch.setattr(sources.store, "_connect", named_connect)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(repository.heartbeat, claim)
            assert wait_for_lock(sources.store, "curriculum-expiry-wait", future)
            blocker.execute("SELECT pg_sleep(0.6)")
            blocker.commit()
            assert future.result(timeout=5) is False
    assert read_run(ingestion, run).status == "running"
    assert repository.recover_expired(principal.tenant_id, project.id, run.id)


@pytest.mark.parametrize("target", ["source", "context", "project"])
def test_run_children_and_command_snapshots_cascade_on_dependency_delete(ingestion, target):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion, multiple=True)
    run = create_run(ingestion, context=context)
    repository = RunRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    with sources.store._connect() as connection:
        connection.execute(
            """INSERT INTO curriculum_run_checkpoints
               (tenant_id,project_id,run_id,sequence,attempt_number,stage,workflow_version,payload,content_sha256)
               VALUES (%s,%s,%s,1,1,'validated','curriculum-workflow-v1','{"copied":"synthetic source text"}',%s)""",
            (principal.tenant_id, project.id, run.id, "a" * 64),
        )
        connection.execute(
            """INSERT INTO curriculum_model_calls
               (tenant_id,project_id,run_id,call_id,attempt_number,purpose,provider,model,model_digest,request_sha256,
                engine,prompt_version,input_characters)
               VALUES (%s,%s,%s,%s,1,'generate','ollama-local','synthetic-model',%s,%s,'synthetic-engine','prompt-v1',10)""",
            (principal.tenant_id, project.id, run.id, uuid4(), "b" * 64, "c" * 64),
        )
    repository.cancel(principal.tenant_id, project.id, actor, run.id, RunCommand(idempotency_key="cascade-cancel-key"))
    calls = state_rows(ingestion, run, "curriculum_model_calls")
    assert calls[0]["status"] == "interrupted" and calls[0]["failure_code"] == "cancelled"
    assert all(calls[0][key] is None for key in ("input_tokens", "output_tokens", "output_characters", "duration_ms"))
    assert len(state_rows(ingestion, run, "curriculum_run_commands")) == 1
    if target == "context":
        with sources.store._connect() as connection:
            connection.execute("DELETE FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.id))
    elif target == "source":
        # Delete an unused source from the multi-source context as well.
        with sources.store._connect() as connection:
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.request.selected_sources[-1].source_id))
    else:
        with sources.store._connect() as connection:
            connection.execute("DELETE FROM projects WHERE tenant_id=%s AND id=%s", (principal.tenant_id, project.id))
    for table in ("curriculum_run_attempts", "curriculum_run_commands", "curriculum_run_outbox",
                  "curriculum_run_checkpoints", "curriculum_model_calls"):
        assert state_rows(ingestion, run, table) == []
    assert repository.claim(principal.tenant_id, project.id, run.id) is None
    assert not repository.heartbeat(claim)
    assert not repository.recover_expired(principal.tenant_id, project.id, run.id)


def test_membership_revocation_waits_for_claim_then_blocks_heartbeat(ingestion, monkeypatch):
    sources, _, principal, project, actor = ingestion
    run = create_run(ingestion)
    repository = RunRepository(sources.store)
    reached, release = Event(), Event()
    original_context = repository._context
    def held_context(*args):
        result = original_context(*args)
        reached.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(repository, "_context", held_context)
    def revoke():
        with sources.store._connect() as connection:
            connection.execute("SET application_name='curriculum-revoke-wait'")
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    with ThreadPoolExecutor(max_workers=2) as pool:
        claim_future = pool.submit(repository.claim, principal.tenant_id, project.id, run.id)
        assert reached.wait(5)
        revoke_future = pool.submit(revoke)
        assert wait_for_lock(sources.store, "curriculum-revoke-wait", revoke_future)
        release.set()
        claim = claim_future.result(timeout=5)
        revoke_future.result(timeout=5)
    monkeypatch.setattr(repository, "_context", original_context)
    assert claim is not None and not repository.heartbeat(claim)
    with sources.store._connect() as connection:
        row = connection.execute("SELECT status,failure_code FROM curriculum_runs WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                 (principal.tenant_id, project.id, run.id)).fetchone()
    assert row == {"status": "failed", "failure_code": "authorization_revoked"}


def test_claim_fences_direct_source_cleanup_without_source_lock_inversion(ingestion, monkeypatch):
    sources, _, principal, project, _ = ingestion
    context = saved_context(ingestion)
    run = create_run(ingestion, context=context)
    repository = RunRepository(sources.store)
    reached, release = Event(), Event()
    original_context = repository._context
    def held_context(*args):
        result = original_context(*args)
        reached.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(repository, "_context", held_context)
    def delete_source():
        with sources.store._connect() as connection:
            connection.execute("SET application_name='curriculum-source-wait'")
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.request.selected_sources[0].source_id))
    with ThreadPoolExecutor(max_workers=2) as pool:
        claim_future = pool.submit(repository.claim, principal.tenant_id, project.id, run.id)
        assert reached.wait(5)
        delete_future = pool.submit(delete_source)
        assert wait_for_lock(sources.store, "curriculum-source-wait", delete_future)
        release.set()
        claim = claim_future.result(timeout=5)
        delete_future.result(timeout=5)
    monkeypatch.setattr(repository, "_context", original_context)
    assert claim is not None
    assert repository.claim(principal.tenant_id, project.id, run.id) is None
    assert not repository.heartbeat(claim)
    assert state_rows(ingestion, run, "curriculum_run_attempts") == []


@pytest.mark.parametrize("operation", ["create", "fail", "retry"])
def test_outbox_failure_rolls_back_entire_transition(ingestion, monkeypatch, operation):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = RunRepository(sources.store)
    run = create_run(ingestion, context=context) if operation != "create" else None
    claim = repository.claim(principal.tenant_id, project.id, run.id) if operation == "fail" else None
    if operation == "retry":
        repository.cancel(principal.tenant_id, project.id, actor, run.id,
                          RunCommand(idempotency_key="rollback-cancel-key"))
    before = read_run(ingestion, run) if run is not None else None
    def fail_outbox(*_):
        raise RuntimeError("synthetic insertion failure")
    monkeypatch.setattr(RunRepository, "_enqueue", staticmethod(fail_outbox))
    with pytest.raises(RuntimeError, match="synthetic insertion failure"):
        if operation == "create":
            repository.create(principal.tenant_id, project.id, actor, context.id,
                              RunCreate(idempotency_key="rollback-create-key", workflow_version="workflow-v1"))
        elif operation == "fail":
            repository.fail(claim, "provider_timeout", retryable=True)
        else:
            repository.retry(principal.tenant_id, project.id, actor, run.id,
                             RunCommand(idempotency_key="rollback-retry-key"))
    if run is not None:
        assert read_run(ingestion, run) == before
        if operation == "fail":
            assert state_rows(ingestion, run, "curriculum_run_attempts")[0]["status"] == "running"
        else:
            assert len(state_rows(ingestion, run, "curriculum_run_commands")) == 1
    else:
        with sources.store._connect() as connection:
            assert connection.execute("SELECT count(*) AS n FROM curriculum_runs").fetchone()["n"] == 0
            assert connection.execute("SELECT count(*) AS n FROM curriculum_run_outbox").fetchone()["n"] == 0
