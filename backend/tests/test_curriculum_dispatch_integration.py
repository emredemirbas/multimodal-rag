"""Scoped durable curriculum dispatch and scheduler recovery, without a broker."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.run_contracts import CheckpointSave
from app.curriculum.runs import RunRepository
from app.jobs.curriculum_dispatch import dispatch_once, recover_expired, redeliver_unclaimed
from test_curriculum_drafts_integration import saved_context
from test_curriculum_runs_integration import create_run, read_run, state_rows
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def test_broker_failure_releases_delivery_lease_and_retries_only_this_outbox(ingestion, caplog):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    store = sources.store

    def unavailable(*_):
        raise ConnectionError("do-not-log-this-broker-password")

    assert dispatch_once(store, unavailable) == 0
    row = state_rows(ingestion, run, "curriculum_run_outbox")[0]
    assert row["publish_attempts"] == 1 and row["sent_at"] is None
    assert row["lease_token"] is row["lease_expires_at"] is None
    assert read_run(ingestion, run).attempt_count == 0
    assert dispatch_once(store, lambda *_: pytest.fail("Delivery must respect its retry delay")) == 0
    with store._connect() as connection:
        connection.execute(
            "UPDATE curriculum_run_outbox SET available_at=clock_timestamp()-interval '1 second' "
            "WHERE tenant_id=%s AND project_id=%s AND run_id=%s", (principal.tenant_id, project.id, run.id))
    messages = []
    assert dispatch_once(store, lambda *message: messages.append(message)) == 1
    assert messages == [(principal.tenant_id, project.id, run.id)]
    row = state_rows(ingestion, run, "curriculum_run_outbox")[0]
    assert row["publish_attempts"] == 2 and row["sent_at"] is not None
    assert row["lease_token"] is row["lease_expires_at"] is None
    assert "do-not-log-this" not in caplog.text
    assert '"event": "curriculum_delivery_unavailable"' in caplog.text


def test_concurrent_dispatch_does_not_hold_database_locks_during_broker_call(ingestion):
    sources, _, principal, project, _ = ingestion
    context = saved_context(ingestion)
    first_run = create_run(ingestion, key="first-dispatch-key", context=context)
    second_run = create_run(ingestion, key="second-dispatch-key", context=context)
    entered, release = Event(), Event()
    first_messages, second_messages = [], []

    def paused_publish(*message):
        first_messages.append(message)
        entered.set()
        assert release.wait(10), "The second dispatcher was blocked by the broker call"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatch_once, sources.store, paused_publish, limit=1)
        try:
            assert entered.wait(5)
            second = pool.submit(dispatch_once, sources.store, lambda *message: second_messages.append(message), limit=1)
            assert second.result(timeout=5) == 1
        finally:
            release.set()
        assert first.result(timeout=5) == 1
    messages = first_messages + second_messages
    assert len(messages) == 2
    assert {message[:2] for message in messages} == {(principal.tenant_id, project.id)}
    assert {message[2] for message in messages} == {first_run.id, second_run.id}
    assert dispatch_once(sources.store, lambda *_: pytest.fail("Already published")) == 0


def test_old_publish_ack_cannot_fence_out_a_fast_workers_next_checkpoint_delivery(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    delivery = RunDeliveryRepository(sources.store)

    def process_before_publisher_returns(tenant, project_id, run_id):
        claim = delivery.claim(tenant, project_id, run_id)
        assert claim is not None
        assert delivery.continue_with_checkpoint(claim, CheckpointSave(
            sequence=1, stage="accepted-stage", payload={"accepted": True}))

    assert dispatch_once(sources.store, process_before_publisher_returns) == 1
    continued = read_run(ingestion, run)
    assert continued.status == "pending" and continued.checkpoint_seq == 1
    assert continued.attempt_count == 1 and continued.failure_count == 0
    row = state_rows(ingestion, run, "curriculum_run_outbox")[0]
    assert row["sent_at"] is row["lease_token"] is row["lease_expires_at"] is None
    messages = []
    assert dispatch_once(sources.store, lambda *message: messages.append(message)) == 1
    assert messages == [(principal.tenant_id, project.id, run.id)]
    assert state_rows(ingestion, run, "curriculum_run_outbox")[0]["sent_at"] is not None


def test_sent_unclaimed_delivery_rearms_after_delay_but_running_run_does_not(ingestion):
    sources, _, principal, project, _ = ingestion
    run = create_run(ingestion)
    scope = (principal.tenant_id, project.id, run.id)
    assert dispatch_once(sources.store, lambda *_: None) == 1
    assert redeliver_unclaimed(sources.store) == 0

    def age_publication():
        with sources.store._connect() as connection:
            connection.execute(
                "UPDATE curriculum_run_outbox SET sent_at=clock_timestamp()-interval '61 seconds' "
                "WHERE tenant_id=%s AND project_id=%s AND run_id=%s", scope)

    age_publication()
    assert redeliver_unclaimed(sources.store) == 1
    row = state_rows(ingestion, run, "curriculum_run_outbox")[0]
    assert row["sent_at"] is row["lease_token"] is row["lease_expires_at"] is None
    assert dispatch_once(sources.store, lambda *_: None) == 1
    assert RunRepository(sources.store).claim(*scope) is not None
    age_publication()
    assert redeliver_unclaimed(sources.store) == 0
    assert state_rows(ingestion, run, "curriculum_run_outbox")[0]["sent_at"] is not None


def test_scheduler_recovery_is_bounded_and_exhausts_only_the_lost_runs_budget(ingestion):
    sources, _, principal, project, _ = ingestion
    context = saved_context(ingestion)
    runs = [create_run(ingestion, key=f"recovery-budget-{index}", context=context) for index in range(3)]
    repository = RunRepository(sources.store)
    for run in runs:
        assert repository.claim(principal.tenant_id, project.id, run.id) is not None
    with sources.store._connect() as connection:
        connection.execute(
            "UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id))
    assert recover_expired(sources.store, limit=1) == 1
    assert sorted(read_run(ingestion, run).status for run in runs) == ["retrying", "running", "running"]
    assert recover_expired(sources.store) == 2
    assert recover_expired(sources.store) == 0
    for run in runs:
        observed = read_run(ingestion, run)
        assert observed.failure_count == 1 and observed.failure_code == "worker_lost"
    selected = runs[0]
    scope = (principal.tenant_id, project.id, selected.id)
    for expected_failures in (2, 3):
        with sources.store._connect() as connection:
            connection.execute(
                "UPDATE curriculum_runs SET available_at=clock_timestamp()-interval '1 second' "
                "WHERE tenant_id=%s AND project_id=%s AND id=%s", scope)
        assert repository.claim(*scope) is not None
        with sources.store._connect() as connection:
            connection.execute(
                "UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE tenant_id=%s AND project_id=%s AND id=%s", scope)
        assert recover_expired(sources.store) == 1
        assert read_run(ingestion, selected).failure_count == expected_failures
    assert read_run(ingestion, selected).status == "failed"
    assert state_rows(ingestion, selected, "curriculum_run_outbox") == []
    assert all(read_run(ingestion, run).failure_count == 1 for run in runs[1:])
    assert recover_expired(sources.store) == 0
