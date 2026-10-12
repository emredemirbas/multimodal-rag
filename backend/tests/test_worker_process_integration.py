"""Kill only a test-owned Celery process, with isolated DB schema and Redis key prefix."""
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from celery import Celery
import pytest
from redis import Redis

from app.artifacts.storage import S3ArtifactStore
from app.jobs.dispatch import dispatch_once
from test_ingestion_integration import ingestion, register
from test_postgres_integration import isolated_postgres_url

WORKER_CODE = '''
import os,time
from app.jobs.worker import celery_app
from app.artifacts.storage import S3ArtifactStore
celery_app.conf.broker_transport_options = {**celery_app.conf.broker_transport_options, 'global_keyprefix': os.environ['PROBE_PREFIX']}
if os.environ.get('PROBE_PAUSE') == '1':
    original = S3ArtifactStore.get
    def paused(self, key, limit):
        content = original(self, key, limit)
        time.sleep(120)
        return content
    S3ArtifactStore.get = paused
elif os.environ.get('PROBE_DELAY'):
    original = S3ArtifactStore.get
    def delayed(self, key, limit):
        content = original(self, key, limit)
        time.sleep(float(os.environ['PROBE_DELAY']))
        return content
    S3ArtifactStore.get = delayed
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
                       '--without-gossip','--without-mingle','--without-heartbeat',
                       '--queues='+os.environ['PROBE_QUEUE'],'--hostname='+os.environ['PROBE_QUEUE']+os.environ.get('PROBE_HOST_SUFFIX','')])
'''


@pytest.mark.integration
@pytest.mark.worker_integration
def test_actual_worker_death_recovery_and_duplicate_delivery(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1':
        pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO available')
    repository, service, principal, project, actor = ingestion
    password = os.environ['MINIO_ROOT_PASSWORD']
    settings = replace(repository.settings,
                       s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
                       s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=password)
    artifacts = S3ArtifactStore(settings)
    repository.artifacts = artifacts
    broker = os.getenv('TEST_REDIS_URL', f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6380')}/0")
    prefix = 'ingestion-probe-'+uuid4().hex+':'
    queue = 'probe-'+uuid4().hex
    client = Celery('worker_probe', broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix': prefix, 'socket_connect_timeout': 3, 'socket_timeout': 5}
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix+'*'))
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
           'APP_ENV': 'test', 'DATABASE_URL': repository.store.database_url,
           'S3_ENDPOINT': settings.s3_endpoint, 'S3_ACCESS_KEY': settings.s3_access_key,
           'S3_SECRET_KEY': settings.s3_secret_key, 'CELERY_BROKER_URL': broker,
           'AUTH_MODE': 'development', 'DEVELOPMENT_AUTH_TOKEN': 'probe-development-token',
           'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive',
           'PROBE_PREFIX': prefix, 'PROBE_QUEUE': queue}
    workers = []

    def start(paused):
        worker = subprocess.Popen([sys.executable, '-c', WORKER_CODE], env={**env, 'PROBE_PAUSE': '1' if paused else '0'},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(worker)
        return worker

    def publish(row):
        client.send_task('tutorial.process_transcript', args=[row['tenant_id'], str(row['project_id']), str(row['source_id']), str(row['job_id']), row['generation']], queue=queue, expires=60)

    def wait(status):
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            job = repository.get_job(principal.tenant_id, project.id, result.job.id)
            if job.status == status:
                return job
            time.sleep(0.1)
        raise AssertionError(f'Test-owned worker did not reach {status}')

    try:
        result = register(ingestion)
        first_worker = start(True)
        assert dispatch_once(repository, publish) == 1
        wait('running')
        first_worker.kill()
        first_worker.wait(timeout=5)
        # Advance this schema's lease after a real SIGKILL, without waiting three minutes.
        with repository.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, result.job.id))
        assert repository.recover_leases() == 1
        with repository.store._connect() as connection:
            connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id, project.id, result.job.id))
            connection.execute('UPDATE outbox_events SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, result.job.id))
        start(False)
        assert dispatch_once(repository, publish) == 1
        completed = wait('succeeded')
        assert completed.attempt_count == 2
        # Re-deliver the completed logical job through the actual broker.
        publish({'tenant_id': principal.tenant_id, 'project_id': project.id, 'source_id': result.source.id, 'job_id': result.job.id, 'generation': 1})
        time.sleep(0.5)
        assert repository.get_job(principal.tenant_id, project.id, result.job.id).attempt_count == 2
        with repository.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS count FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (principal.tenant_id, project.id, result.source.id)).fetchone()['count'] == 1
        assert not service.ask(principal, project.id, 'What is GET /health?').abstained
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        artifacts.delete_prefix(f'{principal.tenant_id}/{project.id}/')
        # Resolve exact keys within our unique namespace, never flush a shared Redis DB.
        keys = list(redis.scan_iter(match=prefix+'*'))
        if keys:
            redis.delete(*keys)
        client.close()
