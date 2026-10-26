"""Actual queue/MinIO/process-loss test; inference is an explicit synthetic fixture."""
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
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import register_video, scope


WORKER_CODE = '''
import os,time,psycopg
from app.jobs.visual_worker import celery_app
from app.jobs import visual_processing
from app.artifacts.storage import S3ArtifactStore
from app.vision.checkpoints import VisualCheckpoints
from test_visual_service import identity,result
class FixtureVisual:
    def ready(self,language): return identity(language)
    def extract(self,data,*,expected_identity):
        with psycopg.connect(os.environ['DATABASE_URL']) as connection:
            connection.execute('INSERT INTO probe_visual_calls(tenant_id,project_id,job_id) VALUES(%s,%s,%s)',
                (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_JOB']))
        return result(data)
def provider(settings):
    if os.environ['PROBE_PAUSE'] == '0': raise AssertionError('Cached result must skip provider construction')
    return FixtureVisual()
visual_processing.build_visual_provider=provider
if os.environ['PROBE_PAUSE'] == '1':
    save=VisualCheckpoints.save
    def save_and_pause(self,*args,**kwargs):
        saved=save(self,*args,**kwargs)
        if saved: time.sleep(120)
        return saved
    VisualCheckpoints.save=save_and_pause
else:
    def forbidden_get(*args,**kwargs): raise AssertionError('Cached result must skip original GET')
    S3ArtifactStore.get=forbidden_get
celery_app.conf.broker_transport_options={**celery_app.conf.broker_transport_options,'global_keyprefix':os.environ['PROBE_PREFIX']}
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
    '--without-gossip','--without-mingle','--without-heartbeat',
    '--queues='+os.environ['PROBE_QUEUE'],'--hostname='+os.environ['PROBE_QUEUE']])
'''


@pytest.mark.integration
@pytest.mark.worker_integration
def test_actual_visual_sigkill_resumes_saved_result_without_get_or_provider_and_retires_minio(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1':
        pytest.skip('Set TEST_REAL_WORKER=1 with disposable Redis and MinIO')
    repo, service, principal, project, actor = ingestion
    repo.settings = replace(repo.settings,
        s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts = S3ArtifactStore(repo.settings)
    broker = os.getenv('TEST_REDIS_URL', f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6380')}/0")
    prefix, queue = 'visual-probe-' + uuid4().hex + ':', 'visual-' + uuid4().hex
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix + '*'))
    client = Celery('visual_probe', broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix': prefix, 'socket_connect_timeout': 3, 'socket_timeout': 5}
    workers = []
    with repo.store._connect() as connection:
        connection.execute('CREATE TABLE probe_visual_calls(tenant_id text,project_id uuid,job_id uuid)')
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]),
        'APP_ENV': 'test', 'DATABASE_URL': repo.store.database_url, 'S3_ENDPOINT': repo.settings.s3_endpoint,
        'S3_ACCESS_KEY': repo.settings.s3_access_key, 'S3_SECRET_KEY': repo.settings.s3_secret_key,
        'CELERY_BROKER_URL': broker, 'AUTH_MODE': 'development', 'DEVELOPMENT_AUTH_TOKEN': 'probe-development-token',
        'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive',
        'PROBE_PREFIX': prefix, 'PROBE_QUEUE': queue, 'PROBE_TENANT': principal.tenant_id, 'PROBE_PROJECT': str(project.id)}

    def start(pause):
        worker = subprocess.Popen([sys.executable, '-c', WORKER_CODE],
            env={**env, 'PROBE_JOB': str(item.job.id), 'PROBE_PAUSE': '1' if pause else '0'},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(worker)
        return worker

    def publish(row):
        assert row['job_type'] == 'visual'
        client.send_task('tutorial.process_video', args=[row['tenant_id'], str(row['project_id']), str(row['source_id']),
            str(row['job_id']), row['generation']], queue=queue, expires=60)

    try:
        item = register_video(ingestion)
        first = start(True)
        assert dispatch_once(repo, publish) == 1
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            with repo.store._connect() as connection:
                row = connection.execute('SELECT saved_at FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()
            if row and row['saved_at'] is not None: break
            assert first.poll() is None, 'Owned visual worker exited before checkpoint'
            time.sleep(.1)
        else: raise AssertionError('Owned visual worker did not save its fixture checkpoint')
        first.kill()
        first.wait(timeout=5)
        with repo.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(item))
        assert repo.recover_leases() == 1
        make_due(repo, item)
        second = start(False)
        assert dispatch_once(repo, publish) == 1
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            completed = repo.get_job(*scope(item))
            if completed.status == 'succeeded': break
            assert completed.status != 'failed', completed.failure_code
            assert second.poll() is None
            time.sleep(.1)
        else: raise AssertionError('Replacement visual worker did not prepare cached result')
        assert completed.stage == 'visual_prepared' and completed.attempt_count == completed.delivery_count == 2
        publish({'job_type': 'visual', 'tenant_id': principal.tenant_id, 'project_id': project.id,
                 'source_id': item.source.id, 'job_id': item.job.id, 'generation': 1})
        time.sleep(.3)
        assert repo.get_job(*scope(item)).delivery_count == 2
        with repo.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM probe_visual_calls WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['n'] == 1
            assert connection.execute('SELECT count(*) AS n FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['n'] == 1
            raw = connection.execute('SELECT object_key FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['object_key']
            assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames').fetchone()['n'] == 2
        assert repo.artifacts.client.head_object(Bucket=repo.artifacts.bucket, Key=raw)['ContentType'] == 'video/mp4'
        assert cleanup_once(repo) == 1
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
        assert service.ask(principal, project.id, 'GET /health').abstained
        current = repo.get_source(principal.tenant_id, project.id, item.source.id)
        assert current.status == 'metadata_ready' and current.active_generation is None
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try: worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        ticket = service.delete_project(principal, project.id)
        for _ in range(10):
            if not cleanup_once(repo): break
        assert repo.get_cleanup(principal.tenant_id, project.id, ticket, actor).status == 'completed'
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
        keys = list(redis.scan_iter(match=prefix + '*'))
        if keys: redis.delete(*keys)
        client.close()
