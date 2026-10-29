"""Real scoped receipts and authored HTTP inference; no native model."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event
from uuid import uuid4

import psycopg
import pytest

from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.execution import StageFailure
from app.curriculum.model_calls import LeasedCurriculumCalls
from app.curriculum.run_contracts import ModelCallStart, RunCommand
from app.sources.contracts import SourceError
from test_curriculum_local_provider import local_curriculum_server, spec
from test_curriculum_runs_integration import create_run, make_due, state_rows
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


@pytest.fixture
def call_setup(ingestion, local_curriculum_server):
    sources, _, principal, project, _ = ingestion
    provider, state = local_curriculum_server
    run = create_run(ingestion)
    repository = RunDeliveryRepository(sources.store)
    claim = repository.claim(principal.tenant_id, project.id, run.id)
    return ingestion, run, repository, claim, provider, state, LeasedCurriculumCalls(repository, provider)


@pytest.mark.parametrize("usage", [(123, 35), (None, None), (0, 0)])
def test_exact_receipt_commits_before_http_inference_and_usage_stays_private(call_setup, usage, caplog):
    ing, run, repo, claim, provider, state, calls = call_setup
    prepared = provider.prepare(spec())
    state["override"] = {"prompt_eval_count": usage[0], "eval_count": usage[1]}
    def check_receipt(_):
        rows = state_rows(ing, run, "curriculum_model_calls")
        assert len(rows) == 1 and rows[0]["status"] == "started"
        assert rows[0]["input_sha256"] == sha256(prepared.payload).hexdigest()
        assert rows[0]["input_tokens"] is rows[0]["duration_ms"] is None
    state["on_chat"] = check_receipt
    result = calls.invoke(claim, spec())
    assert result is not None
    row = state_rows(ing, run, "curriculum_model_calls")[0]
    assert row["status"] == "succeeded" and row["model_digest"] == provider.identity.model_digest
    assert row["engine"] == provider.identity.engine and row["schema_version"] == spec().schema_version
    assert row["request_version"] == "curriculum-json-call-v1" and row["input_sha256"] == result.input_sha256
    assert (row["input_tokens"], row["output_tokens"]) == usage
    assert row["output_characters"] == len(result.content) and row["duration_ms"] == result.duration_ms
    assert row["billed_usd"] == 0 and "PRIVATE" not in str(row) and "PRIVATE" not in caplog.text
    with repo.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM curriculum_drafts").fetchone()["n"] == 0


def retire(ing, run, repo, boundary):
    sources, service, principal, project, actor = ing
    if boundary == "cancelled":
        repo.cancel(principal.tenant_id, project.id, actor, run.id, RunCommand(idempotency_key="cancel-model-inference"))
    elif boundary == "expired": make_due(ing, run, expired=True)
    elif boundary == "archive": service.archive_project(principal, project.id)
    else:
        with sources.store._connect() as connection:
            if boundary == "revoked":
                connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
            elif boundary == "source-delete":
                connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id))
            else:
                connection.execute("DELETE FROM projects WHERE tenant_id=%s AND id=%s", (principal.tenant_id, project.id))


@pytest.mark.parametrize("boundary", ["token", "tenant", "expired", "cancelled", "archive", "revoked"])
def test_lost_admission_never_calls_inference_or_writes_a_receipt(call_setup, boundary):
    ing, run, repo, claim, _, state, calls = call_setup
    if boundary == "token": claim = claim.model_copy(update={"lease_token": uuid4()})
    elif boundary == "tenant": claim = claim.model_copy(update={"tenant_id": "foreign-tenant"})
    else: retire(ing, run, repo, boundary)
    assert calls.invoke(claim, spec()) is None
    assert "/api/chat" not in state["calls"] and state_rows(ing, run, "curriculum_model_calls") == []


@pytest.mark.parametrize("boundary", ["cancelled", "expired", "archive", "revoked", "source-delete", "project-delete"])
def test_no_database_lock_during_inference_and_late_output_is_discarded(call_setup, boundary):
    ing, run, repo, claim, _, state, calls = call_setup
    entered, release = Event(), Event()
    def pause(_):
        entered.set()
        assert release.wait(10)
    state["on_chat"] = pause
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(calls.invoke, claim, spec())
        try:
            assert entered.wait(5)
            assert state_rows(ing, run, "curriculum_model_calls")[0]["status"] == "started"
            pool.submit(retire, ing, run, repo, boundary).result(timeout=5)
        finally:
            release.set()
        assert future.result(timeout=5) is None
    if boundary == "expired":
        assert repo.recover_expired(claim.tenant_id, claim.project_id, claim.run_id)
    rows = state_rows(ing, run, "curriculum_model_calls")
    assert len(rows) == (0 if boundary.endswith("delete") else 1)
    assert all(row["status"] == "interrupted" and row["output_tokens"] is None for row in rows)


@pytest.mark.parametrize("failure", ["invalid", "drift", "missing"])
def test_provider_failures_finish_only_started_receipts_with_known_usage(call_setup, failure):
    ing, run, _, claim, _, state, calls = call_setup
    if failure == "invalid": state["content"] = '{"duplicate":1,"duplicate":2}'
    if failure == "drift": state["on_chat"] = lambda _: state["version"].update(version="0.40.4")
    if failure == "missing": state["tags"]["models"] = []
    with pytest.raises(StageFailure) as error:
        calls.invoke(claim, spec())
    assert error.value.code == ("invalid_output" if failure == "invalid" else "provider_unavailable")
    rows = state_rows(ing, run, "curriculum_model_calls")
    assert len(rows) == (0 if failure == "missing" else 1)
    for row in rows:
        assert row["status"] == "failed" and row["failure_code"] == error.value.code
        assert row["input_tokens"] == 123 and row["output_tokens"] == 35 and row["duration_ms"] >= 0


def test_receipt_commit_failure_prevents_physical_inference(call_setup):
    ing, run, repo, claim, _, state, calls = call_setup
    with repo.store._connect() as connection:
        connection.execute("""CREATE FUNCTION reject_call_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Synthetic interrupted commit' USING ERRCODE='40001'; END $$""")
        connection.execute("""CREATE CONSTRAINT TRIGGER reject_call_commit AFTER INSERT ON curriculum_model_calls
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_call_commit()""")
    with pytest.raises(psycopg.errors.SerializationFailure):
        calls.invoke(claim, spec())
    assert "/api/chat" not in state["calls"] and state_rows(ing, run, "curriculum_model_calls") == []


@pytest.mark.parametrize("operation", ["start", "finish"])
def test_lease_expiry_during_receipt_write_cannot_authorize_or_return_output(call_setup, operation):
    ing, run, repo, claim, _, state, calls = call_setup
    def near_expiry(_=None):
        with repo.store._connect() as connection:
            connection.execute("UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()+interval '0.3 seconds' "
                               "WHERE tenant_id=%s AND project_id=%s AND id=%s", (claim.tenant_id, claim.project_id, claim.run_id))
    with repo.store._connect() as connection:
        connection.execute("""CREATE FUNCTION pause_call_write() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.5); RETURN NEW; END $$""")
        action = "INSERT" if operation == "start" else "UPDATE"
        connection.execute(f"CREATE TRIGGER pause_call_write BEFORE {action} ON curriculum_model_calls "
                           "FOR EACH ROW EXECUTE FUNCTION pause_call_write()")
    if operation == "start": near_expiry()
    else: state["on_chat"] = near_expiry
    assert calls.invoke(claim, spec()) is None
    rows = state_rows(ing, run, "curriculum_model_calls")
    if operation == "start": assert "/api/chat" not in state["calls"] and rows == []
    else: assert rows[0]["status"] == "started" and rows[0]["output_tokens"] is None


@pytest.mark.parametrize("field", ["input_sha256", "schema_version", "request_version"])
def test_same_call_key_cannot_be_reused_for_different_prepared_request(call_setup, field):
    ing, run, repo, claim, _, _, calls = call_setup
    assert calls.invoke(claim, spec())
    row = state_rows(ing, run, "curriculum_model_calls")[0]
    start = ModelCallStart(**({name: row[name] for name in ModelCallStart.model_fields} | {"input_tokens": None}))
    replay = repo.begin_call(claim, start)
    assert replay.status == "succeeded" and replay.created_at == row["created_at"]
    altered = start.model_copy(update={field: "b"*64 if field == "input_sha256" else "different-v2"})
    with pytest.raises(SourceError) as error:
        repo.begin_call(claim, altered)
    assert error.value.code == "model_call_conflict"
