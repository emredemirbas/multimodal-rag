"""Real curriculum worker loss, with a test-only processor and isolated Redis keys.

No model, MinIO or owner service is used. The processor below exists only in the
test child, so these recovery fixtures cannot become a product generation path.
"""

import os
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from celery import Celery
import pytest
from redis import Redis

from app.curriculum.run_contracts import RunCreate
from app.curriculum.runs import RunRepository
from app.jobs.curriculum_dispatch import dispatch_once, recover_expired
from test_curriculum_drafts_integration import content_for, saved_context
from test_curriculum_local_provider import local_curriculum_server
from test_curriculum_workflow import authored_reply
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


WORKER_CODE = '''
import os,time
import psycopg
from app.curriculum.contracts import AssignmentContent
from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.execution import StageResult
from app.curriculum.run_contracts import CheckpointSave
from app.jobs.curriculum_worker import celery_app,PROCESSORS

def record(stage):
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        connection.execute('INSERT INTO probe_curriculum_stages(tenant_id,project_id,run_id,stage) VALUES(%s,%s,%s,%s)',
            (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_RUN'],stage))

def fixture_processor(stage_input):
    if os.environ['PROBE_BOUNDARY'] == 'after_checkpoint_commit' and not stage_input.checkpoints:
        record('prepare')
        return StageResult(checkpoint=CheckpointSave(sequence=1,stage='prepared',payload={'prepared':True}))
    record('publish')
    if os.environ['PROBE_PAUSE'] == 'before_final_commit':
        record('before_final_commit')
        time.sleep(120)
    return StageResult(content=AssignmentContent.model_validate_json(os.environ['PROBE_CONTENT']))

PROCESSORS['probe-curriculum-v1'] = fixture_processor
if os.environ.get('PROBE_GRAPH_ENDPOINT'):
    from app.curriculum.local_provider import LocalCurriculumProvider,LocalModelIdentity
    from app.curriculum.model_calls import LeasedCurriculumCalls
    from app.curriculum.workflow import TutorialAssignmentWorkflow,WORKFLOW_VERSION
    from app.jobs.curriculum_worker import settings
    from app.postgres import PostgresStore
    PROCESSORS[WORKFLOW_VERSION] = TutorialAssignmentWorkflow(LeasedCurriculumCalls(
        RunDeliveryRepository(PostgresStore(settings.database_url)),LocalCurriculumProvider(os.environ['PROBE_GRAPH_ENDPOINT'],
            LocalModelIdentity(model_digest='a'*64,engine='0.40.3'))))
if os.environ['PROBE_PAUSE'] == 'after_checkpoint_commit':
    original_continue = RunDeliveryRepository.continue_with_checkpoint
    def checkpoint_and_pause(self,*args,**kwargs):
        saved = original_continue(self,*args,**kwargs)
        if saved and args[1].stage == os.environ.get('PROBE_CHECKPOINT_STAGE','prepared'):
            record('after_checkpoint_commit')
            time.sleep(120)
        return saved
    RunDeliveryRepository.continue_with_checkpoint = checkpoint_and_pause

@celery_app.task(name='probe.curriculum_barrier')
def barrier():
    record('barrier')

celery_app.conf.broker_transport_options = {
    **celery_app.conf.broker_transport_options,'global_keyprefix':os.environ['PROBE_PREFIX']}
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
    '--without-gossip','--without-mingle','--without-heartbeat',
    '--queues='+os.environ['PROBE_QUEUE'],'--hostname='+os.environ['PROBE_QUEUE']])
'''


pytestmark = [pytest.mark.integration, pytest.mark.curriculum_worker_integration]


@pytest.mark.parametrize("boundary", ["before_final_commit", "after_checkpoint_commit"])
def test_actual_sigkill_recovery_commits_one_draft_and_reuses_accepted_stage(ingestion, boundary):
    if os.getenv("TEST_CURRICULUM_WORKER") != "1":
        pytest.skip("Set TEST_CURRICULUM_WORKER=1 with an isolated Redis broker")
    broker = os.environ["TEST_CURRICULUM_REDIS_URL"]
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    runs = RunRepository(sources.store)
    run = runs.create(principal.tenant_id, project.id, actor, context.id, RunCreate(
        idempotency_key="process-recovery-run", workflow_version="probe-curriculum-v1"))
    with sources.store._connect() as connection:
        connection.execute("CREATE TABLE probe_curriculum_stages(tenant_id text,project_id uuid,run_id uuid,stage text)")
    scope = (principal.tenant_id, project.id, run.id)
    prefix, queue = "curriculum-probe-" + uuid4().hex + ":", "curriculum-probe-" + uuid4().hex
    client = Celery("curriculum_probe", broker=broker)
    client.conf.broker_transport_options = {
        "global_keyprefix": prefix, "socket_connect_timeout": 3, "socket_timeout": 5,
    }
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix + "*"))
    env = {
        **os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "APP_ENV": "test",
        "DATABASE_URL": sources.store.database_url, "CELERY_BROKER_URL": broker,
        "AUTH_MODE": "development", "DEVELOPMENT_AUTH_TOKEN": "probe-development-token",
        "EMBEDDING_PROVIDER": "hash", "ANSWER_PROVIDER": "extractive",
        "PROBE_TENANT": principal.tenant_id, "PROBE_PROJECT": str(project.id), "PROBE_RUN": str(run.id),
        "PROBE_PREFIX": prefix, "PROBE_QUEUE": queue, "PROBE_BOUNDARY": boundary,
        "PROBE_CONTENT": content_for(context).model_dump_json(),
    }
    workers = []

    def start(pause):
        process = subprocess.Popen([sys.executable, "-c", WORKER_CODE], env={**env, "PROBE_PAUSE": pause},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(process)
        return process

    def publish(tenant_id, project_id, run_id):
        client.send_task("curriculum.advance_run", args=[tenant_id, str(project_id), str(run_id)],
                         queue=queue, expires=60)

    def stages():
        with sources.store._connect() as connection:
            return [row["stage"] for row in connection.execute(
                "SELECT stage FROM probe_curriculum_stages WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
                scope).fetchall()]

    def current():
        return runs.read(principal.tenant_id, project.id, actor, run.id)

    def wait_until(predicate, description):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if predicate():
                return
            assert workers[-1].poll() is None, "The test-owned worker exited before " + description
            observed = current()
            assert observed.status not in {"failed", "cancelled"}, observed.failure_code
            time.sleep(0.1)
        raise AssertionError("The test-owned worker did not reach " + description)

    try:
        first = start(boundary)
        assert dispatch_once(sources.store, publish) == 1
        wait_until(lambda: boundary in stages(), boundary)
        first.kill()
        first.wait(timeout=5)
        interrupted = current()
        assert interrupted.attempt_count == 1
        with sources.store._connect() as connection:
            assert connection.execute(
                "SELECT count(*) AS n FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s",
                scope[:2]).fetchone()["n"] == 0
        if boundary == "before_final_commit":
            assert interrupted.status == "running" and interrupted.checkpoint_seq == 0
            # Advance only this run's lease after a real SIGKILL; no three-minute sleep.
            with sources.store._connect() as connection:
                connection.execute(
                    "UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE tenant_id=%s AND project_id=%s AND id=%s", scope)
            assert recover_expired(sources.store) == 1
            with sources.store._connect() as connection:
                connection.execute(
                    "UPDATE curriculum_runs SET available_at=clock_timestamp()-interval '1 second' "
                    "WHERE tenant_id=%s AND project_id=%s AND id=%s", scope)
                connection.execute(
                    "UPDATE curriculum_run_outbox SET available_at=clock_timestamp()-interval '1 second' "
                    "WHERE tenant_id=%s AND project_id=%s AND run_id=%s", scope)
        else:
            assert interrupted.status == "pending" and interrupted.checkpoint_seq == 1
            assert interrupted.failure_count == 0
            assert recover_expired(sources.store) == 0
        start("continue")
        assert dispatch_once(sources.store, publish) == 1
        wait_until(lambda: current().status == "succeeded", "a committed draft")
        completed = current()
        assert completed.attempt_count == 2
        assert completed.failure_count == (1 if boundary == "before_final_commit" else 0)
        assert completed.checkpoint_seq == (0 if boundary == "before_final_commit" else 1)
        assert completed.result_draft_id is not None and completed.result_revision == 1
        expected_calls = ["publish", "publish"] if boundary == "before_final_commit" else ["prepare", "publish"]
        assert sorted(stage for stage in stages() if stage in {"prepare", "publish"}) == sorted(expected_calls)

        # Two completed-run deliveries pass through the real broker. A FIFO barrier
        # proves the single worker consumed them before uniqueness is asserted.
        publish(*scope)
        publish(*scope)
        client.send_task("probe.curriculum_barrier", queue=queue, expires=60)
        wait_until(lambda: "barrier" in stages(), "duplicate delivery acknowledgement")
        assert current() == completed
        assert sorted(stage for stage in stages() if stage in {"prepare", "publish"}) == sorted(expected_calls)
        with sources.store._connect() as connection:
            for table in ("curriculum_drafts", "curriculum_draft_revisions", "curriculum_run_results"):
                assert connection.execute(
                    f"SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s", scope[:2]
                ).fetchone()["n"] == 1
            assert connection.execute(
                "SELECT count(*) AS n FROM curriculum_run_outbox WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
                scope).fetchone()["n"] == 0
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        # Only this test's random namespace; never flush the Redis database.
        keys = list(redis.scan_iter(match=prefix + "*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        client.close()


def test_actual_graph_resumes_after_sigkill_without_repeating_accepted_extraction(ingestion, local_curriculum_server):
    if os.getenv("TEST_CURRICULUM_WORKER") != "1":
        pytest.skip("Set TEST_CURRICULUM_WORKER=1 with an isolated Redis broker")
    from app.curriculum.workflow import WORKFLOW_VERSION
    broker = os.environ["TEST_CURRICULUM_REDIS_URL"]
    sources, _, principal, project, actor = ingestion
    provider, state = local_curriculum_server
    phases = []
    def reply(request):
        body = json.loads(request["messages"][1]["content"])
        phases.append(body["stage"])
        state["content"] = json.dumps(authored_reply(body))
    state["on_chat"] = reply
    context = saved_context(ingestion)
    runs = RunRepository(sources.store)
    run = runs.create(principal.tenant_id, project.id, actor, context.id,
        RunCreate(idempotency_key="graph-process-recovery", workflow_version=WORKFLOW_VERSION))
    with sources.store._connect() as connection:
        connection.execute("CREATE TABLE probe_curriculum_stages(tenant_id text,project_id uuid,run_id uuid,stage text)")
    scope = (principal.tenant_id, project.id, run.id)
    prefix, queue = "curriculum-graph-" + uuid4().hex + ":", "curriculum-graph-" + uuid4().hex
    client = Celery("curriculum_graph_probe", broker=broker)
    client.conf.broker_transport_options = {"global_keyprefix": prefix, "socket_connect_timeout": 3, "socket_timeout": 5}
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix + "*"))
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "APP_ENV": "test",
        "DATABASE_URL": sources.store.database_url, "CELERY_BROKER_URL": broker,
        "AUTH_MODE": "development", "DEVELOPMENT_AUTH_TOKEN": "probe-development-token",
        "EMBEDDING_PROVIDER": "hash", "ANSWER_PROVIDER": "extractive",
        "PROBE_TENANT": principal.tenant_id, "PROBE_PROJECT": str(project.id), "PROBE_RUN": str(run.id),
        "PROBE_PREFIX": prefix, "PROBE_QUEUE": queue, "PROBE_BOUNDARY": "graph",
        "PROBE_GRAPH_ENDPOINT": provider.base_url, "PROBE_CHECKPOINT_STAGE": "curriculum.extracted"}
    workers = []

    def start(pause):
        process = subprocess.Popen([sys.executable, "-c", WORKER_CODE], env={**env, "PROBE_PAUSE": pause},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(process)
        return process

    def publish(tenant, project_id, run_id):
        client.send_task("curriculum.advance_run", args=[tenant, str(project_id), str(run_id)], queue=queue, expires=60)

    def current():
        return runs.read(principal.tenant_id, project.id, actor, run.id)

    def recorded(name):
        with sources.store._connect() as connection:
            return connection.execute("SELECT 1 FROM probe_curriculum_stages WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND stage=%s",
                                      (*scope, name)).fetchone() is not None

    def wait_until(predicate):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if predicate():
                return
            assert workers[-1].poll() is None, "The test-owned graph worker exited"
            assert current().status not in {"failed", "cancelled"}, current().failure_code
            dispatch_once(sources.store, publish)
            time.sleep(.1)
        pytest.fail("The test-owned graph worker did not reach the checkpoint/result")

    try:
        first = start("after_checkpoint_commit")
        wait_until(lambda: recorded("after_checkpoint_commit"))
        first.kill()
        first.wait(timeout=5)
        interrupted = current()
        assert interrupted.status == "pending" and interrupted.checkpoint_seq == 2
        assert interrupted.failure_count == 0 and phases == ["extract"]
        start("continue")
        wait_until(lambda: current().status == "succeeded")
        completed = current()
        assert completed.attempt_count == 4 and completed.checkpoint_seq == 3 and completed.failure_count == 0
        assert completed.result_draft_id is not None and phases == ["extract", "select", "generate"]
        publish(*scope)
        publish(*scope)
        client.send_task("probe.curriculum_barrier", queue=queue, expires=60)
        wait_until(lambda: recorded("barrier"))
        assert current() == completed and phases == ["extract", "select", "generate"]
        with sources.store._connect() as connection:
            for table in ("curriculum_drafts", "curriculum_draft_revisions", "curriculum_run_results"):
                assert connection.execute(f"SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s", scope[:2]).fetchone()["n"] == 1
            assert connection.execute("SELECT count(*) AS n FROM curriculum_model_calls WHERE tenant_id=%s AND project_id=%s AND run_id=%s", scope).fetchone()["n"] == 3
            payload = connection.execute("SELECT payload FROM curriculum_run_checkpoints WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND stage='curriculum.extracted'", scope).fetchone()["payload"]
            accepted = payload["accepted"][0]["extraction"]
            assert accepted["goals"][0]["id"] == "goal0" and "insufficient" not in accepted
            assert accepted["coverage"][0]["goal_ids"] == ["goal0"]
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        keys = list(redis.scan_iter(match=prefix + "*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        client.close()
