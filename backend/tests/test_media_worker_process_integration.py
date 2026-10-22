"""Actual dedicated queues/MinIO/process loss with explicit fixture inference."""
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
from app.jobs.dispatch import cleanup_once, dispatch_once
from app.jobs.queue import delivery_route
from app.models import AuthorizationMode
from app.sources.media import MediaRepository
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_wav import wav_bytes
from test_worker_process_integration import WORKER_CODE


@pytest.mark.integration
@pytest.mark.worker_integration
def test_actual_media_sigkill_resumes_windows_then_hands_off_to_ingestion_and_cleans_minio(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1':
        pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO available')
    repo, service, principal, project, actor = ingestion
    repo.settings = replace(repo.settings,
        s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts = S3ArtifactStore(repo.settings)
    broker = os.getenv('TEST_REDIS_URL', f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6380')}/0")
    prefix, media_queue, ingestion_queue = 'media-probe-' + uuid4().hex + ':', 'media-' + uuid4().hex, 'index-' + uuid4().hex
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix + '*'))
    client = Celery('media_probe', broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix': prefix, 'socket_connect_timeout': 3, 'socket_timeout': 5}
    workers = []
    with repo.store._connect() as connection:
        connection.execute('CREATE TABLE probe_asr_calls(tenant_id text,project_id uuid,job_id uuid,ordinal integer)')
    try:
        result = MediaRepository(repo).register(principal.tenant_id, project.id, actor, filename='owned.wav',
            content=wav_bytes(496000), rights=AuthorizationMode.OWNER_UPLOAD, language='en', idempotency_key='actual-media-probe')
    except Exception:
        repo.artifacts.delete_prefix(f'{principal.tenant_id}/{project.id}/')
        client.close()
        raise
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'APP_ENV': 'test',
        'DATABASE_URL': repo.store.database_url, 'S3_ENDPOINT': repo.settings.s3_endpoint,
        'S3_ACCESS_KEY': repo.settings.s3_access_key, 'S3_SECRET_KEY': repo.settings.s3_secret_key,
        'CELERY_BROKER_URL': broker, 'AUTH_MODE': 'development', 'DEVELOPMENT_AUTH_TOKEN': 'probe-development-token',
        'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive',
        'PROBE_PREFIX': prefix, 'PROBE_TENANT': principal.tenant_id, 'PROBE_PROJECT': str(project.id), 'PROBE_JOB': str(result.job.id)}

    def start(media, pause=False):
        worker = subprocess.Popen([sys.executable, '-c', WORKER_CODE],
            env={**env, 'PROBE_QUEUE': media_queue if media else ingestion_queue,
                 'PROBE_MEDIA': '1' if media else '0', 'PROBE_ASR_PAUSE': '1' if pause else '0'},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(worker)
        return worker

    def publish(row):
        task, queue = delivery_route(row['job_type'])
        client.send_task(task, args=[row['tenant_id'], str(row['project_id']), str(row['source_id']), str(row['job_id']), row['generation']],
                         queue=media_queue if queue == 'media' else ingestion_queue, expires=60)

    try:
        first = start(True, True)
        assert dispatch_once(repo, publish) == 1
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            with repo.store._connect() as connection:
                row = connection.execute('SELECT next_window FROM asr_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                                         (principal.tenant_id, project.id, result.job.id)).fetchone()
            if row and row['next_window'] == 1:
                break
            assert first.poll() is None, 'Test-owned media worker exited before saving a window'
            time.sleep(.1)
        else:
            raise AssertionError('Test-owned media worker did not checkpoint')
        first.kill()
        first.wait(timeout=5)
        with repo.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, result.job.id))
        assert repo.recover_leases() == 1
        make_due(repo, result)
        start(True)
        start(False)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            dispatch_once(repo, publish)
            current = repo.get_source(principal.tenant_id, project.id, result.source.id)
            if current.status == 'ready':
                break
            assert current.status not in {'failed', 'cancelled'}, current.failure_code
            time.sleep(.1)
        else:
            raise AssertionError('Dedicated media/ingestion queues did not finish their handoff')
        completed = repo.get_job(principal.tenant_id, project.id, result.job.id)
        assert completed.status == 'succeeded' and completed.attempt_count == 2 and completed.delivery_count == 2
        with repo.store._connect() as connection:
            scope = (principal.tenant_id, project.id, result.job.id)
            calls = connection.execute('SELECT ordinal,count(*) AS n FROM probe_asr_calls WHERE tenant_id=%s AND project_id=%s AND job_id=%s GROUP BY ordinal ORDER BY ordinal', scope).fetchall()
            assert [(row['ordinal'], row['n']) for row in calls] == [(0, 1), (1, 1)]
            raw = connection.execute('SELECT object_key FROM audio_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope).fetchone()['object_key']
        publish({'job_type': 'asr', 'tenant_id': principal.tenant_id, 'project_id': project.id,
                 'source_id': result.source.id, 'job_id': result.job.id, 'generation': 1})
        time.sleep(.3)
        assert repo.get_job(principal.tenant_id, project.id, result.job.id).delivery_count == 2
        assert repo.artifacts.client.head_object(Bucket=repo.artifacts.bucket, Key=raw)['ContentType'] == 'audio/wav'
        assert cleanup_once(repo) == 1
        objects = repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents', [])
        assert raw not in [item['Key'] for item in objects] and len(objects) == 1
        answer = service.ask(principal, project.id, 'GET /health')
        assert not answer.abstained and answer.citations[0].source_id == result.source.id
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        ticket = service.delete_project(principal, project.id)
        for _ in range(10):
            if not cleanup_once(repo):
                break
        assert repo.get_cleanup(principal.tenant_id, project.id, ticket, actor).status == 'completed'
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
        keys = list(redis.scan_iter(match=prefix + '*'))
        if keys:
            redis.delete(*keys)
        client.close()
