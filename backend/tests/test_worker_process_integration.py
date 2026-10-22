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
if os.environ.get('PROBE_MEDIA') == '1':
    import psycopg
    from app.jobs.media_worker import celery_app
    from app.jobs import media_processing
    from app.asr.checkpoints import AsrCheckpoints
    from app.asr.contracts import TranscriptionSlice
    from app.asr.profile import identity
    class FixtureSpeech:
        def transcribe(self,pcm,language):
            with psycopg.connect(os.environ['DATABASE_URL']) as connection:
                ordinal=connection.execute('SELECT next_window FROM asr_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                    (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_JOB'])).fetchone()[0]
                connection.execute('INSERT INTO probe_asr_calls(tenant_id,project_id,job_id,ordinal) VALUES(%s,%s,%s,%s)',
                    (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_JOB'],ordinal))
            return TranscriptionSlice.model_validate({**identity(),'input_frames':len(pcm)//2,'requested_language':language,
                'language':'en','language_probability':.9,'duration_ms':17,
                'segments':[{'start_ms':0,'end_ms':900,'text':'GET /health reports service health.'}]})
    media_processing.build_transcription_provider=lambda settings: FixtureSpeech()
    if os.environ.get('PROBE_ASR_PAUSE') == '1':
        save=AsrCheckpoints.save
        def save_and_pause(self,*args,**kwargs):
            saved=save(self,*args,**kwargs)
            if saved: time.sleep(120)
            return saved
        AsrCheckpoints.save=save_and_pause
celery_app.conf.broker_transport_options = {**celery_app.conf.broker_transport_options, 'global_keyprefix': os.environ['PROBE_PREFIX']}
if os.environ.get('PROBE_SEMANTIC') == '1':
    import re,psycopg
    from app.jobs import processing
    from app.jobs.checkpoints import TranscriptCheckpoints
    from app.embedding_profiles import QWEN_SPACE,QWEN_MODEL,QWEN_DIGEST
    from app.providers import EmbeddingBatch
    class FixtureEmbeddings:
        name,model,model_digest,space_id,dimensions = 'ollama-local',QWEN_MODEL,QWEN_DIGEST,QWEN_SPACE,1024
        def embed_documents(self,texts):
            with psycopg.connect(os.environ['DATABASE_URL']) as connection:
                for text in texts:
                    number=int(re.search(r'Chunk (\\d+)\\.',text).group(1))
                    connection.execute('INSERT INTO probe_embedding_calls(tenant_id,project_id,source_id,chunk_number) VALUES(%s,%s,%s,%s)',
                        (os.environ['PROBE_TENANT'],os.environ['PROBE_PROJECT'],os.environ['PROBE_SOURCE'],number))
            return EmbeddingBatch([[1.]+[0.]*1023 for text in texts],len(texts)*12)
    processing.build_embedding_provider=lambda settings: FixtureEmbeddings()
    if os.environ.get('PROBE_CHECKPOINT_PAUSE') == '1':
        checkpoint_save=TranscriptCheckpoints.save
        def save_and_pause(self,*args,**kwargs):
            saved=checkpoint_save(self,*args,**kwargs)
            if saved: time.sleep(120)
            return saved
        TranscriptCheckpoints.save=save_and_pause
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


@pytest.mark.integration
@pytest.mark.worker_integration
def test_actual_sigkill_after_checkpoint_resumes_without_duplicate_embeddings(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1':
        pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO available')
    from app.jobs.dispatch import cleanup_once
    from test_checkpoints_integration import long_transcript, make_due
    repo, service, principal, project, actor = ingestion
    repo.settings = replace(repo.settings,embedding_provider='ollama',
        s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT','9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER','tutorial'),s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts = S3ArtifactStore(repo.settings)
    broker = os.getenv('TEST_REDIS_URL',f"redis://127.0.0.1:{os.getenv('REDIS_PORT','6380')}/0")
    prefix, queue = 'checkpoint-probe-'+uuid4().hex+':', 'checkpoint-'+uuid4().hex
    redis = Redis.from_url(broker); redis.ping()
    assert not list(redis.scan_iter(match=prefix+'*'))
    client = Celery('checkpoint_probe',broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix':prefix,'socket_connect_timeout':3,'socket_timeout':5}
    with repo.store._connect() as connection:
        connection.execute('CREATE TABLE probe_embedding_calls(tenant_id text,project_id uuid,source_id uuid,chunk_number integer)')
    result = register(ingestion,content=long_transcript(129))
    env = {**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'APP_ENV':'test',
        'DATABASE_URL':repo.store.database_url,'S3_ENDPOINT':repo.settings.s3_endpoint,
        'S3_ACCESS_KEY':repo.settings.s3_access_key,'S3_SECRET_KEY':repo.settings.s3_secret_key,
        'CELERY_BROKER_URL':broker,'AUTH_MODE':'development','DEVELOPMENT_AUTH_TOKEN':'probe-development-token',
        'EMBEDDING_PROVIDER':'ollama','ANSWER_PROVIDER':'extractive','PROBE_PREFIX':prefix,'PROBE_QUEUE':queue,
        'PROBE_SEMANTIC':'1','PROBE_TENANT':principal.tenant_id,'PROBE_PROJECT':str(project.id),'PROBE_SOURCE':str(result.source.id)}
    workers = []
    def start(paused):
        worker = subprocess.Popen([sys.executable,'-c',WORKER_CODE],env={**env,'PROBE_CHECKPOINT_PAUSE':'1' if paused else '0'},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        workers.append(worker); return worker
    def publish(row):
        client.send_task('tutorial.process_transcript',args=[row['tenant_id'],str(row['project_id']),str(row['source_id']),str(row['job_id']),row['generation']],queue=queue,expires=60)
    try:
        first = start(True)
        assert dispatch_once(repo,publish) == 1
        deadline = time.monotonic()+25
        while time.monotonic()<deadline:
            job = repo.get_job(principal.tenant_id,project.id,result.job.id)
            if job.processed_segments == 8: break
            assert job.status not in {'failed','cancelled'}, job.failure_code
            time.sleep(.1)
        else: raise AssertionError('Test-owned worker did not commit its first checkpoint')
        first.kill(); first.wait(timeout=5)
        with repo.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id,project.id,result.job.id))
        assert repo.recover_leases() == 1
        make_due(repo,result); start(False)
        deadline = time.monotonic()+35
        while time.monotonic()<deadline:
            dispatch_once(repo,publish)
            job = repo.get_job(principal.tenant_id,project.id,result.job.id)
            if job.status == 'succeeded': break
            assert job.status not in {'failed','cancelled'}, job.failure_code
            time.sleep(.1)
        else: raise AssertionError('Replacement worker did not finish checkpointed deliveries')
        assert job.attempt_count == 2 and job.delivery_count == 3 and job.processed_segments == 129
        with repo.store._connect() as connection:
            scope = (principal.tenant_id,project.id,result.source.id)
            calls = connection.execute('SELECT chunk_number,count(*) AS n FROM probe_embedding_calls WHERE tenant_id=%s AND project_id=%s AND source_id=%s GROUP BY chunk_number ORDER BY chunk_number',scope).fetchall()
            assert [row['chunk_number'] for row in calls] == list(range(129)) and all(row['n']==1 for row in calls)
            assert connection.execute('SELECT count(*) AS n FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s AND source_id=%s',scope).fetchone()['n'] == 0
            assert connection.execute('SELECT count(*) AS n FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s',scope).fetchone()['n'] == 129
        publish({'tenant_id':principal.tenant_id,'project_id':project.id,'source_id':result.source.id,'job_id':result.job.id,'generation':1})
        time.sleep(.3)
        assert repo.get_job(principal.tenant_id,project.id,result.job.id).delivery_count == 3
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try: worker.wait(timeout=5)
                except subprocess.TimeoutExpired: worker.kill(); worker.wait(timeout=5)
        cleanup = service.delete_project(principal,project.id)
        assert cleanup_once(repo) == 1 and repo.get_cleanup(principal.tenant_id,project.id,cleanup,actor).status == 'completed'
        keys = list(redis.scan_iter(match=prefix+'*'))
        if keys: redis.delete(*keys)
        client.close()
