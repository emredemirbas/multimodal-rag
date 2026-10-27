"""Actual owned Celery SIGKILL after saved OCR embeddings, no native inference."""
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from celery import Celery
import pytest
from redis import Redis

from app.jobs.dispatch import cleanup_once, dispatch_once
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_index_integration import long_gallery, queue_index

WORKER_CODE = '''
import hashlib,os,time,psycopg
from app.jobs.worker import celery_app
from app.providers import DeterministicHashEmbeddingProvider
from app.vision.index import VisualIndexRepository
from app.artifacts.storage import S3ArtifactStore
def forbidden(*args,**kwargs): raise AssertionError('OCR indexing must not read or write source objects')
S3ArtifactStore.get=forbidden
S3ArtifactStore.put=forbidden
embed=DeterministicHashEmbeddingProvider.embed_documents
def counted(self,texts):
    with psycopg.connect(os.environ['DATABASE_URL']) as connection:
        for text in texts:
            connection.execute('INSERT INTO probe_ocr_calls (digest) VALUES (%s)',(hashlib.sha256(text.encode()).hexdigest(),))
    return embed(self,texts)
DeterministicHashEmbeddingProvider.embed_documents=counted
save=VisualIndexRepository.save
def paused(self,claim,offset,batch):
    accepted=save(self,claim,offset,batch)
    if accepted and os.environ['PROBE_PAUSE']=='1': time.sleep(120)
    return accepted
VisualIndexRepository.save=paused
celery_app.conf.broker_transport_options={**celery_app.conf.broker_transport_options,'global_keyprefix':os.environ['PROBE_PREFIX']}
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
    '--without-gossip','--without-mingle','--without-heartbeat',
    '--queues='+os.environ['PROBE_QUEUE'],'--hostname='+os.environ['PROBE_QUEUE']])
'''


@pytest.mark.integration
@pytest.mark.worker_integration
def test_killed_ocr_worker_resumes_committed_batch_without_object_or_native_access(ingestion):
    if os.getenv('TEST_REAL_WORKER') != '1': pytest.skip('Set TEST_REAL_WORKER=1 with Redis')
    repo,service,principal,project,actor=ingestion
    text=''.join((f'part{i}: user_id '+'x'*1200)[:1200] for i in range(13))+'TAILuser_id'
    _,publication=long_gallery(ingestion,text=text,count=1)
    item=queue_index(ingestion,publication)
    broker=os.environ['TEST_REDIS_URL']; prefix='ocr-probe-'+uuid4().hex+':'; queue='ocr-'+uuid4().hex
    redis=Redis.from_url(broker); redis.ping()
    client=Celery('ocr_probe',broker=broker)
    client.conf.broker_transport_options={'global_keyprefix':prefix,'socket_connect_timeout':3,'socket_timeout':5}
    workers=[]
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'DATABASE_URL':repo.store.database_url,
        'APP_ENV':'test','AUTH_MODE':'development','DEVELOPMENT_AUTH_TOKEN':'probe-development-token',
        'EMBEDDING_PROVIDER':'hash','ANSWER_PROVIDER':'extractive','CELERY_BROKER_URL':broker,
        'S3_ACCESS_KEY':'unused-fixture-key','S3_SECRET_KEY':'unused-fixture-secret',
        'PROBE_PREFIX':prefix,'PROBE_QUEUE':queue}
    def start(pause):
        worker=subprocess.Popen([sys.executable,'-c',WORKER_CODE],env={**env,'PROBE_PAUSE':'1' if pause else '0'},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        workers.append(worker); return worker
    def publish(row):
        assert row['job_type']=='visual_index'
        client.send_task('tutorial.index_visual',args=[row['tenant_id'],str(row['project_id']),str(row['source_id']),str(row['job_id']),row['generation']],queue=queue,expires=60)
    try:
        with repo.store._connect() as connection:
            connection.execute('CREATE TABLE probe_ocr_calls(digest text)')
            connection.execute('UPDATE outbox_events SET sent_at=now() WHERE tenant_id=%s AND project_id=%s AND job_id<>%s',(principal.tenant_id,project.id,item.job.id))
        first=start(True); assert dispatch_once(repo,publish)==1
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            current=repo.get_job(principal.tenant_id,project.id,item.job.id)
            if current.processed_segments==8: break
            assert first.poll() is None
            assert current.status!='failed',current.failure_code
            time.sleep(.1)
        else: raise AssertionError('Owned OCR worker did not save first batch')
        assert repo.get_source(principal.tenant_id,project.id,item.source.id).active_generation is None
        first.kill(); first.wait(timeout=5)
        with repo.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s",(principal.tenant_id,project.id,item.job.id))
        assert repo.recover_leases()==1
        make_due(repo,item); second=start(False); assert dispatch_once(repo,publish)==1
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            current=repo.get_job(principal.tenant_id,project.id,item.job.id)
            if current.status=='succeeded': break
            assert current.status!='failed',current.failure_code
            assert second.poll() is None
            time.sleep(.1)
        else: raise AssertionError('Replacement OCR worker did not finish')
        assert current.processed_segments==14 and current.delivery_count==2 and current.attempt_count==2
        with repo.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM probe_ocr_calls').fetchone()['n']==14
            assert connection.execute('SELECT max(n) AS n FROM (SELECT count(*) AS n FROM probe_ocr_calls GROUP BY digest) counts').fetchone()['n']==1
            assert connection.execute('SELECT count(*) AS n FROM visual_index_chunks').fetchone()['n']==0
            assert connection.execute('SELECT count(*) AS n FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchone()['n']==1
        assert not service.ask(principal,project.id,'user_id').abstained
        publish(dict(tenant_id=principal.tenant_id,project_id=project.id,source_id=item.source.id,job_id=item.job.id,generation=item.job.generation,job_type='visual_index'))
        time.sleep(.3)
        assert repo.get_job(principal.tenant_id,project.id,item.job.id).delivery_count==2
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try: worker.wait(timeout=5)
                except subprocess.TimeoutExpired: worker.kill(); worker.wait(timeout=5)
        service.delete_project(principal,project.id)
        while cleanup_once(repo): pass
        assert not repo.artifacts.objects
        keys=list(redis.scan_iter(match=prefix+'*'))
        if keys: redis.delete(*keys)
        client.close()
