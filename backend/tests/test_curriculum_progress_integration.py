"""Synthetic PostgreSQL checkpoints and per-call attribution, without inference."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
import psycopg

from app.curriculum.repository import ContextRepository
from app.curriculum.run_contracts import (
    CheckpointSave,
    ModelCallFinish,
    ModelCallStart,
    RunCommand,
    RunCreate,
)
from app.curriculum.run_progress import RunProgressRepository
from app.sources.contracts import SourceError
from test_curriculum_drafts_integration import saved_context
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


@pytest.fixture
def progress(ingestion):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion, key="progress-context", multiple=True)
    repository = RunProgressRepository(sources.store)
    run = repository.create(
        principal.tenant_id, project.id, actor, context.id,
        RunCreate(idempotency_key="progress-run", workflow_version="curriculum-graph-v1"),
    )
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    assert claim is not None
    return SimpleNamespace(sources=sources, service=service, principal=principal,
                           project=project, actor=actor, context=context,
                           repository=repository, run=run, claim=claim)


def checkpoint(sequence=1, **changes):
    return CheckpointSave(sequence=sequence, stage="objectives-v1",
                          payload={"text": "PRIVATE synthetic objective", "ids": [1, None, True],
                                   "nested": {"language": "Türkçe"}}, **changes)


def call_start(**changes):
    values = {"call_id": uuid4(), "purpose": "objectives", "provider": "ollama-local",
              "model": "qwen3:4b", "model_digest": "a" * 64, "engine": "ollama-0.12.0",
              "prompt_version": "objectives-prompt-v1", "input_characters": 123,
              "input_tokens": None}
    return ModelCallStart(**(values | changes))


def call_finish(start, **changes):
    values = {"call_id": start.call_id, "status": "succeeded", "input_tokens": 17,
              "output_tokens": 5, "output_characters": 21, "duration_ms": 10,
              "failure_code": None}
    return ModelCallFinish(**(values | changes))


def stored(progress, table):
    with progress.sources.store._connect() as connection:
        return connection.execute(
            f"SELECT * FROM {table} WHERE tenant_id=%s AND project_id=%s",
            (progress.principal.tenant_id, progress.project.id),
        ).fetchall()


def assert_conflict(action, code):
    with pytest.raises(SourceError) as rejected:
        action()
    assert rejected.value.code == code and rejected.value.status == 409


def assert_invalid(action):
    with pytest.raises(SourceError) as rejected:
        action()
    assert rejected.value.code == "invalid_curriculum_progress" and rejected.value.status == 422
    assert "PRIVATE" not in str(rejected.value)


def make_due(progress):
    with progress.sources.store._connect() as connection:
        connection.execute(
            "UPDATE curriculum_runs SET available_at=clock_timestamp()-interval '1 second' "
            "WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (progress.principal.tenant_id, progress.project.id, progress.run.id),
        )


def assert_fenced(progress, claim, start):
    assert progress.repository.save_checkpoint(claim, checkpoint(2)) is False
    assert progress.repository.load_checkpoints(claim) is None
    assert progress.repository.begin_call(claim, start) is None
    assert progress.repository.finish_call(claim, call_finish(start)) is False


def test_checkpoint_copy_replay_server_owned_identity_and_safe_logs(progress, caplog):
    body = checkpoint()
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        assert progress.repository.save_checkpoint(progress.claim, body)
        assert progress.repository.save_checkpoint(progress.claim, body)
    loaded = progress.repository.load_checkpoints(progress.claim)
    assert len(loaded) == 1
    saved = loaded[0]
    assert (saved.tenant_id, saved.project_id, saved.run_id) == (
        progress.principal.tenant_id, progress.project.id, progress.run.id)
    assert saved.attempt_number == 1 and saved.workflow_version == "curriculum-graph-v1"
    assert saved.sequence == 1 and saved.stage == body.stage and saved.payload == body.payload
    assert len(saved.content_sha256) == 64
    body.payload["text"] = "Mutated caller data"
    saved.payload["text"] = "Mutated response data"
    assert progress.repository.load_checkpoints(progress.claim)[0].payload["text"] == "PRIVATE synthetic objective"
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 1
    messages = "\n".join(record.message for record in caplog.records)
    assert "curriculum_checkpoint_saved" in messages
    assert "PRIVATE" not in messages and "Türkçe" not in messages


def test_checkpoint_order_conflicts_and_persisted_sequence_are_atomic(progress):
    assert_conflict(lambda: progress.repository.save_checkpoint(progress.claim, checkpoint(2)),
                    "checkpoint_sequence_conflict")
    assert not stored(progress, "curriculum_run_checkpoints")
    assert progress.repository.save_checkpoint(progress.claim, checkpoint())
    for changed in [checkpoint().model_copy(update={"stage": "draft-v1"}),
                    checkpoint().model_copy(update={"payload": {"text": "Different PRIVATE content"}})]:
        assert_conflict(lambda: progress.repository.save_checkpoint(progress.claim, changed), "checkpoint_conflict")
    assert_conflict(lambda: progress.repository.save_checkpoint(progress.claim, checkpoint(3)),
                    "checkpoint_sequence_conflict")
    assert progress.repository.save_checkpoint(progress.claim, checkpoint(2))
    assert [item.sequence for item in progress.repository.load_checkpoints(progress.claim)] == [1, 2]
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 2


@pytest.mark.parametrize("changed", [
    {"sequence": True}, {"sequence": 65}, {"stage": "PRIVATE unsafe stage"},
    {"payload": {"value": float("nan")}}, {"payload": {"value": float("inf")}},
    {"payload": {"nested": ["PRIVATE\0value"]}}, {"payload": {"PRIVATE\0key": 1}},
    {"payload": {1: "PRIVATE non-string key"}}, {"payload": ["PRIVATE not an object"]},
    {"payload": {"text": "ü" * 150_000}},
])
def test_forged_or_oversized_checkpoints_are_rejected_without_partial_rows(progress, changed):
    body = CheckpointSave.model_construct(**({"sequence": 1, "stage": "objectives-v1", "payload": {}} | changed))
    assert_invalid(lambda: progress.repository.save_checkpoint(progress.claim, body))
    assert not stored(progress, "curriculum_run_checkpoints")
    assert progress.repository.load_checkpoints(progress.claim) == []
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 0


def test_checkpoint_jsonb_separator_growth_is_bounded_before_insert(progress):
    # Compact JSON fits 300 kB, but PostgreSQL's spaced JSONB exceeds 327,680 B.
    body = CheckpointSave(sequence=1, stage="objectives-v1",
                          payload={f"k{number:05}": 0 for number in range(25_500)})
    assert_invalid(lambda: progress.repository.save_checkpoint(progress.claim, body))
    assert not stored(progress, "curriculum_run_checkpoints")
    assert progress.repository.load_checkpoints(progress.claim) == []


def test_checkpoint_exponent_expansion_is_safely_bounded_before_insert(progress):
    # PostgreSQL JSONB expands each exponent to more than 300 decimal digits.
    body = CheckpointSave(sequence=1, stage="objectives-v1", payload={"values": [1e308] * 1_100})
    assert_invalid(lambda: progress.repository.save_checkpoint(progress.claim, body))
    assert not stored(progress, "curriculum_run_checkpoints")
    assert progress.repository.load_checkpoints(progress.claim) == []
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 0


@pytest.mark.parametrize("payload", [{"x": 1e20}, {"zero": -0.0}])
def test_loaded_checkpoint_replays_after_postgres_normalizes_json_numbers(progress, payload):
    body = CheckpointSave(sequence=1, stage="objectives-v1", payload=payload)
    assert progress.repository.save_checkpoint(progress.claim, body)
    saved = progress.repository.load_checkpoints(progress.claim)[0]
    assert progress.repository.save_checkpoint(
        progress.claim, CheckpointSave(sequence=saved.sequence, stage=saved.stage, payload=saved.payload))
    assert progress.repository.load_checkpoints(progress.claim) == [saved]
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 1


def test_failed_head_update_rolls_back_checkpoint_insert_and_allows_same_retry(progress):
    with progress.sources.store._connect() as connection:
        connection.execute("""
            CREATE FUNCTION reject_curriculum_checkpoint_head() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Synthetic transaction interruption' USING ERRCODE='40001'; END $$
        """)
        connection.execute("""
            CREATE TRIGGER reject_curriculum_checkpoint_head BEFORE UPDATE OF checkpoint_seq
            ON curriculum_runs FOR EACH ROW EXECUTE FUNCTION reject_curriculum_checkpoint_head()
        """)
    with pytest.raises(psycopg.errors.SerializationFailure):
        progress.repository.save_checkpoint(progress.claim, checkpoint())
    assert not stored(progress, "curriculum_run_checkpoints")
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 0
    with progress.sources.store._connect() as connection:
        connection.execute("DROP TRIGGER reject_curriculum_checkpoint_head ON curriculum_runs")
    assert progress.repository.save_checkpoint(progress.claim, checkpoint())
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1


def test_literal_escape_text_is_preserved_and_checkpoint_limit_is_finite(progress):
    body = CheckpointSave(sequence=1, stage="objectives-v1", payload={"text": r"literal \u0000"})
    assert progress.repository.save_checkpoint(progress.claim, body)
    for sequence in range(2, 65):
        assert progress.repository.save_checkpoint(
            progress.claim, CheckpointSave(sequence=sequence, stage="objectives-v1", payload={"step": sequence}))
    snapshots = progress.repository.load_checkpoints(progress.claim)
    assert len(snapshots) == 64 and snapshots[0].payload == body.payload
    assert snapshots[-1].sequence == 64


@pytest.mark.parametrize("same", [True, False])
def test_concurrent_checkpoint_writers_accept_once_or_report_content_conflict(progress, same):
    def write(index):
        body = checkpoint()
        if not same and index:
            body.payload["text"] = "Different PRIVATE content"
        try:
            return progress.repository.save_checkpoint(progress.claim, body)
        except SourceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert results.count(True) == (2 if same else 1)
    if not same:
        assert results.count("checkpoint_conflict") == 1
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1
    assert progress.repository.read(progress.principal.tenant_id, progress.project.id,
                                    progress.actor, progress.run.id).checkpoint_seq == 1


def test_started_call_is_durable_without_inference_and_finish_replays_current_view(progress, caplog):
    start = call_start()
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        accepted = progress.repository.begin_call(progress.claim, start)
    assert accepted is not None
    assert accepted.status == "started" and accepted.input_tokens is None
    assert accepted.output_tokens is None and accepted.output_characters is None
    assert accepted.duration_ms is None and accepted.finished_at is None
    assert accepted.billed_usd == 0 and accepted.attempt_number == 1
    assert accepted.model_digest == "a" * 64 and accepted.prompt_version == start.prompt_version
    assert accepted.engine == start.engine and accepted.provider == "ollama-local"
    rows = stored(progress, "curriculum_model_calls")
    assert len(rows) == 1 and rows[0]["call_id"] == start.call_id
    assert len(rows[0]["request_sha256"]) == 64
    assert not {"prompt", "input_text", "output_text", "response"}.intersection(rows[0])
    receipt = call_finish(start)
    assert progress.repository.finish_call(progress.claim, receipt)
    assert progress.repository.finish_call(progress.claim, receipt)
    replay = progress.repository.begin_call(progress.claim, start)
    assert replay is not None and replay.status == "succeeded"
    assert replay.input_tokens == 17 and replay.output_tokens == 5 and replay.output_characters == 21
    assert replay.duration_ms == 10 and replay.finished_at is not None and replay.billed_usd == 0
    assert replay.created_at == accepted.created_at
    assert len(stored(progress, "curriculum_model_calls")) == 1
    messages = "\n".join(record.message for record in caplog.records)
    assert "curriculum_call_started" in messages and "PRIVATE" not in messages


@pytest.mark.parametrize("status,usage", [("succeeded", None), ("failed", None), ("succeeded", 0), ("failed", 0)])
def test_unknown_and_actual_zero_model_usage_remain_distinct(progress, status, usage):
    start = call_start(input_tokens=usage)
    assert progress.repository.begin_call(progress.claim, start)
    finish = call_finish(start, status=status, input_tokens=usage, output_tokens=usage,
                         output_characters=usage, duration_ms=0,
                         failure_code="provider_timeout" if status == "failed" else None)
    assert progress.repository.finish_call(progress.claim, finish)
    row = stored(progress, "curriculum_model_calls")[0]
    assert row["status"] == status
    assert row["input_tokens"] == row["output_tokens"] == row["output_characters"] == usage
    assert row["duration_ms"] == 0 and row["billed_usd"] == 0


@pytest.mark.parametrize("changed", [
    {"purpose": "draft"}, {"model": "different:local"}, {"model_digest": "b" * 64},
    {"engine": "ollama-0.13.0"}, {"prompt_version": "objectives-prompt-v2"},
    {"input_characters": 124}, {"input_tokens": 1},
])
def test_call_identity_cannot_be_reused_for_changed_declared_request(progress, changed):
    start = call_start()
    assert progress.repository.begin_call(progress.claim, start)
    assert_conflict(lambda: progress.repository.begin_call(progress.claim, start.model_copy(update=changed)),
                    "model_call_conflict")
    assert len(stored(progress, "curriculum_model_calls")) == 1


@pytest.mark.parametrize("changed", [
    {"input_tokens": None}, {"output_tokens": 0}, {"output_characters": 22},
    {"duration_ms": 11}, {"status": "failed", "failure_code": "invalid_output"},
])
def test_terminal_model_call_receipt_is_immutable(progress, changed):
    start = call_start()
    progress.repository.begin_call(progress.claim, start)
    finish = call_finish(start)
    assert progress.repository.finish_call(progress.claim, finish)
    assert_conflict(lambda: progress.repository.finish_call(progress.claim, finish.model_copy(update=changed)),
                    "model_call_conflict")
    assert progress.repository.finish_call(progress.claim, finish)
    assert stored(progress, "curriculum_model_calls")[0]["output_tokens"] == 5


@pytest.mark.parametrize("kind,changed", [
    ("start", {"provider": "paid-cloud"}), ("start", {"input_tokens": True}),
    ("start", {"model_digest": "PRIVATE not a digest"}),
    ("finish", {"input_tokens": -1}), ("finish", {"duration_ms": True}),
    ("finish", {"status": "succeeded", "failure_code": "invalid_output"}),
    ("finish", {"status": "failed", "failure_code": None}),
    ("finish", {"status": "failed", "failure_code": "PRIVATE failure details"}),
])
def test_forged_model_call_values_leave_no_attribution_mutation(progress, kind, changed):
    start = call_start()
    if kind == "start":
        assert_invalid(lambda: progress.repository.begin_call(progress.claim, start.model_copy(update=changed)))
        assert not stored(progress, "curriculum_model_calls")
    else:
        progress.repository.begin_call(progress.claim, start)
        assert_invalid(lambda: progress.repository.finish_call(progress.claim, call_finish(start).model_copy(update=changed)))
        assert stored(progress, "curriculum_model_calls")[0]["status"] == "started"


def test_finish_cannot_create_a_call_that_was_not_recorded_before_invocation(progress):
    assert progress.repository.finish_call(progress.claim, call_finish(call_start())) is False
    assert not stored(progress, "curriculum_model_calls")


@pytest.mark.parametrize("same", [True, False])
def test_concurrent_begin_calls_persist_one_request_identity(progress, same):
    start = call_start()

    def begin(index):
        body = start if same or not index else start.model_copy(update={"prompt_version": "prompt-v2"})
        try:
            return progress.repository.begin_call(progress.claim, body)
        except SourceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(begin, range(2)))
    assert sum(not isinstance(item, str) for item in results) == (2 if same else 1)
    if not same:
        assert results.count("model_call_conflict") == 1
    assert len(stored(progress, "curriculum_model_calls")) == 1


def test_model_call_count_is_bounded_but_existing_identity_can_replay(progress):
    first = call_start()
    assert progress.repository.begin_call(progress.claim, first)
    for _ in range(255):
        assert progress.repository.begin_call(progress.claim, call_start())
    assert progress.repository.begin_call(progress.claim, first).call_id == first.call_id
    assert_invalid(lambda: progress.repository.begin_call(progress.claim, call_start()))
    assert len(stored(progress, "curriculum_model_calls")) == 256


@pytest.mark.parametrize("changed", [
    {"tenant_id": "foreign-progress-tenant"}, {"project_id": uuid4()}, {"run_id": uuid4()},
    {"lease_token": uuid4()}, {"attempt_number": 2}, {"attempt_number": True},
])
def test_foreign_or_forged_claim_cannot_read_or_commit_progress(progress, changed):
    start = call_start()
    progress.repository.save_checkpoint(progress.claim, checkpoint())
    progress.repository.begin_call(progress.claim, start)
    assert_fenced(progress, progress.claim.model_copy(update=changed), start)
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1
    assert stored(progress, "curriculum_model_calls")[0]["status"] == "started"


@pytest.mark.parametrize("terminal", ["cancel", "fail", "expired", "revoked", "archived"])
def test_terminal_or_expired_worker_cannot_read_or_write_and_started_usage_stays_unknown(progress, terminal):
    start = call_start()
    progress.repository.save_checkpoint(progress.claim, checkpoint())
    progress.repository.begin_call(progress.claim, start)
    if terminal == "cancel":
        progress.repository.cancel(progress.principal.tenant_id, progress.project.id,
                                   progress.actor, progress.run.id, RunCommand(idempotency_key="cancel-progress"))
    elif terminal == "fail":
        assert progress.repository.fail(progress.claim, "provider_timeout", retryable=False)
    elif terminal == "expired":
        with progress.sources.store._connect() as connection:
            connection.execute(
                "UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (progress.principal.tenant_id, progress.project.id, progress.run.id))
        assert_fenced(progress, progress.claim, start)
        assert progress.repository.recover_expired(progress.principal.tenant_id, progress.project.id, progress.run.id)
    elif terminal == "revoked":
        with progress.sources.store._connect() as connection:
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s",
                               (progress.principal.tenant_id, progress.actor))
    else:
        progress.service.archive_project(progress.principal, progress.project.id)
    assert_fenced(progress, progress.claim, start)
    row = stored(progress, "curriculum_model_calls")[0]
    assert row["status"] == "interrupted" and row["finished_at"] is not None
    assert row["input_tokens"] is row["output_tokens"] is row["output_characters"] is None
    assert row["duration_ms"] is None and row["billed_usd"] == 0
    assert len(stored(progress, "curriculum_run_checkpoints")) == 1


@pytest.mark.parametrize("interruption", ["failure", "worker_lost", "cancel"])
def test_retry_preserves_committed_checkpoints_and_fences_original_attempt_call_identity(progress, interruption):
    start = call_start()
    assert progress.repository.save_checkpoint(progress.claim, checkpoint())
    assert progress.repository.begin_call(progress.claim, start)
    previous = progress.repository.load_checkpoints(progress.claim)[0]
    if interruption == "failure":
        assert progress.repository.fail(progress.claim, "provider_timeout", retryable=True)
    elif interruption == "worker_lost":
        with progress.sources.store._connect() as connection:
            connection.execute(
                "UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (progress.principal.tenant_id, progress.project.id, progress.run.id))
        assert progress.repository.recover_expired(progress.principal.tenant_id, progress.project.id, progress.run.id)
    else:
        progress.repository.cancel(progress.principal.tenant_id, progress.project.id, progress.actor,
                                   progress.run.id, RunCommand(idempotency_key="cancel-preserve-progress"))
        progress.repository.retry(progress.principal.tenant_id, progress.project.id, progress.actor,
                                  progress.run.id, RunCommand(idempotency_key="retry-preserve-progress"))
    make_due(progress)
    replacement = progress.repository.claim(progress.principal.tenant_id, progress.project.id, progress.run.id)
    assert replacement is not None and replacement.attempt_number == 2
    assert replacement.lease_token != progress.claim.lease_token
    assert_fenced(progress, progress.claim, start)
    assert progress.repository.load_checkpoints(replacement) == [previous]
    assert progress.repository.save_checkpoint(replacement, checkpoint())
    assert progress.repository.save_checkpoint(replacement, checkpoint(2))
    assert [item.attempt_number for item in progress.repository.load_checkpoints(replacement)] == [1, 2]
    assert_conflict(lambda: progress.repository.begin_call(replacement, start), "model_call_conflict")
    assert progress.repository.finish_call(replacement, call_finish(start)) is False
    new_start = call_start()
    assert progress.repository.begin_call(replacement, new_start).attempt_number == 2
    assert progress.repository.finish_call(replacement, call_finish(new_start))
    assert [row["status"] for row in sorted(stored(progress, "curriculum_model_calls"),
                                           key=lambda row: row["attempt_number"])] == ["interrupted", "succeeded"]


@pytest.mark.parametrize("target", ["context", "source", "direct_source", "project"])
def test_complete_dependency_deletion_removes_private_progress_and_prevents_resurrection(progress, target):
    start = call_start()
    progress.repository.save_checkpoint(progress.claim, checkpoint())
    progress.repository.begin_call(progress.claim, start)
    progress.repository.cancel(progress.principal.tenant_id, progress.project.id, progress.actor,
                               progress.run.id, RunCommand(idempotency_key="cancel-before-delete"))
    progress.repository.retry(progress.principal.tenant_id, progress.project.id, progress.actor,
                              progress.run.id, RunCommand(idempotency_key="retry-before-delete"))
    replacement = progress.repository.claim(progress.principal.tenant_id, progress.project.id, progress.run.id)
    assert replacement is not None
    if target == "context":
        ContextRepository(progress.sources.store).delete(progress.principal.tenant_id, progress.project.id,
                                                         progress.actor, progress.context.id)
    elif target in {"source", "direct_source"}:
        unused_source = progress.context.request.selected_sources[1].source_id
        if target == "source":
            progress.sources.delete_source(progress.principal.tenant_id, progress.project.id,
                                           unused_source, progress.actor)
        else:
            with progress.sources.store._connect() as connection:
                connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (progress.principal.tenant_id, progress.project.id, unused_source))
    else:
        progress.service.delete_project(progress.principal, progress.project.id)
    for table in ("curriculum_runs", "curriculum_run_attempts", "curriculum_run_outbox",
                  "curriculum_run_commands", "curriculum_run_checkpoints", "curriculum_model_calls"):
        assert stored(progress, table) == [], table
    assert_fenced(progress, progress.claim, start)
    assert_fenced(progress, replacement, start)
    assert stored(progress, "curriculum_run_checkpoints") == []
    assert stored(progress, "curriculum_model_calls") == []
