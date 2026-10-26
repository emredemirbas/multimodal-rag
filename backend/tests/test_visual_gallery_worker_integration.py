"""Actual Celery SIGKILL between S3 PUT and adoption; inference stays synthetic."""
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
from app.vision.gallery import VisualGalleryRepository
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_gallery_integration import prepared

WORKER_CODE = '''
import os,time,psycopg
from app.jobs.visual_worker import celery_app
from app.jobs import visual_processing
from app.artifacts.storage import S3ArtifactStore
def forbidden(settings): raise AssertionError('Derived adoption must never construct the native provider')
visual_processing.build_visual_provider=forbidden
put=S3ArtifactStore.put
def recorded_put(self,key,content):
    put(self,key,content)
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        connection.execute('INSERT INTO probe_frame_puts(tenant_id,project_id,job_id,object_key) VALUES(%s,%s,%s,%s)',
            (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_JOB'],key))
    if os.environ['PROBE_PAUSE'] == '1': time.sleep(120)
S3ArtifactStore.put=recorded_put
celery_app.conf.broker_transport_options={**celery_app.conf.broker_transport_options,'global_keyprefix':os.environ['PROBE_PREFIX']}
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
    '--without-gossip','--without-mingle','--without-heartbeat',
    '--queues='+os.environ['PROBE_QUEUE'],'--hostname='+os.environ['PROBE_QUEUE']])
'''


@pytest.mark.integration
@pytest.mark.worker_integration
def test_actual_put_crash_cleans_only_orphan_and_replacement_retains_png_gallery(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1': pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO')
    repo, service, principal, project, actor = ingestion
    repo.settings = replace(repo.settings,
        s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts = S3ArtifactStore(repo.settings)
    broker = os.getenv('TEST_REDIS_URL', f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6380')}/0")
    prefix, queue = 'gallery-probe-' + uuid4().hex + ':', 'gallery-' + uuid4().hex
    redis = Redis.from_url(broker); redis.ping()
    assert not list(redis.scan_iter(match=prefix + '*'))
    client = Celery('gallery_probe', broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix': prefix, 'socket_connect_timeout': 3, 'socket_timeout': 5}
    workers = []
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'APP_ENV': 'test',
        'DATABASE_URL': repo.store.database_url, 'S3_ENDPOINT': repo.settings.s3_endpoint,
        'S3_ACCESS_KEY': repo.settings.s3_access_key, 'S3_SECRET_KEY': repo.settings.s3_secret_key,
        'CELERY_BROKER_URL': broker, 'AUTH_MODE': 'development', 'DEVELOPMENT_AUTH_TOKEN': 'probe-development-token',
        'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive', 'PROBE_PREFIX': prefix, 'PROBE_QUEUE': queue,
        'PROBE_TENANT': principal.tenant_id, 'PROBE_PROJECT': str(project.id)}

    def start(pause):
        worker = subprocess.Popen([sys.executable, '-c', WORKER_CODE], env={**env, 'PROBE_JOB': str(item.job.id), 'PROBE_PAUSE': '1' if pause else '0'},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        workers.append(worker)
        return worker

    def publish(row):
        assert row['job_type'] == 'visual_publish'
        client.send_task('tutorial.publish_visual', args=[row['tenant_id'], str(row['project_id']), str(row['source_id']), str(row['job_id']), row['generation']], queue=queue, expires=60)

    try:
        original = prepared(ingestion)  # Real S3 input/cleanup; explicit fixture extraction.
        with repo.store._connect() as connection:
            connection.execute('CREATE TABLE probe_frame_puts(tenant_id text,project_id uuid,job_id uuid,object_key text)')
            connection.execute('UPDATE outbox_events SET sent_at=now() WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, original.job.id))
        gallery = VisualGalleryRepository(repo)
        item = gallery.enqueue(principal.tenant_id, project.id, original.source.id, original.job.id, actor, 'actual-gallery-probe')
        first = start(True)
        assert dispatch_once(repo, publish) == 1
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            with repo.store._connect() as connection:
                puts = connection.execute('SELECT object_key FROM probe_frame_puts WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, item.job.id)).fetchall()
            if puts: break
            assert first.poll() is None
            time.sleep(.1)
        else: raise AssertionError('Owned frame worker did not reach the post-PUT boundary')
        orphan = puts[0]['object_key']
        first.kill(); first.wait(timeout=5)
        with repo.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM retained_visual_frames').fetchone()['n'] == 0
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, item.job.id))
            connection.execute('UPDATE artifact_cleanup SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND object_prefix=%s', (principal.tenant_id, project.id, orphan.rsplit('/', 1)[0] + '/'))
        assert cleanup_once(repo) == 1
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=orphan).get('Contents')
        assert repo.recover_leases() == 1
        make_due(repo, item)
        second = start(False)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = repo.get_job(principal.tenant_id, project.id, item.job.id)
            if current.status == 'succeeded': break
            assert current.status != 'failed', current.failure_code
            if current.status in {'pending', 'retrying'}: make_due(repo, item)
            dispatch_once(repo, publish)
            assert second.poll() is None
            time.sleep(.1)
        else: raise AssertionError('Replacement frame worker did not finish retained gallery')
        assert current.stage == 'frames_retained' and current.delivery_count == 3 and current.attempt_count == 2
        view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
        assert len(view.items) == 2 and gallery.image(principal.tenant_id, project.id, view.items[0].id, actor).startswith(b'\x89PNG')
        objects = repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents', [])
        assert len(objects) == 2 and orphan not in {obj['Key'] for obj in objects}
        assert all(repo.artifacts.client.head_object(Bucket=repo.artifacts.bucket, Key=obj['Key'])['ContentType'] == 'image/png' for obj in objects)
        with repo.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM probe_frame_puts').fetchone()['n'] == 3
            assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 1
        publish({'tenant_id': principal.tenant_id, 'project_id': project.id, 'source_id': item.source.id,
                 'job_id': item.job.id, 'generation': 2, 'job_type': 'visual_publish'})
        time.sleep(.3)
        assert repo.get_job(principal.tenant_id, project.id, item.job.id).delivery_count == 3
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try: worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill(); worker.wait(timeout=5)
        ticket = service.delete_project(principal, project.id)
        while cleanup_once(repo): pass
        assert repo.get_cleanup(principal.tenant_id, project.id, ticket, actor).status == 'completed'
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
        keys = list(redis.scan_iter(match=prefix + '*'))
        if keys: redis.delete(*keys)
        client.close()
