"""Owned real Celery process loss after a description commit; fixture model, real S3/Redis/PG."""
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
from app.jobs.dispatch import cleanup_once,dispatch_once
from app.vision.descriptions import DescriptionRepository
from test_checkpoints_integration import make_due
from test_frame_descriptions_integration import queue
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_index_integration import long_gallery

WORKER_CODE='''
import hashlib,os,time,psycopg
from app.jobs.description_worker import celery_app
from app.jobs import descriptions
from app.vision.descriptions import DescriptionRepository
from app.vision.descriptions_client import DescriptionResult,DescriptionIdentity,FrameDescription
class Provider:
    def __init__(self,*args):
        if os.environ['PROBE_PAUSE']=='0': raise AssertionError('Recovery must not create a model provider')
    def ready(self): return DescriptionIdentity(model_digest='a'*64,engine='0.40.3')
    def describe(self,image,width,height,identity):
        with psycopg.connect(os.environ['DATABASE_URL']) as connection:
            connection.execute('INSERT INTO probe_description_calls VALUES (%s)',(hashlib.sha256(image).hexdigest(),))
        return DescriptionResult(identity,FrameDescription(kind='diagram',summary='Two connected boxes.',details=[],uncertainties=[],abstained=False),12,30,5,hashlib.sha256(image).hexdigest())
descriptions.LocalDescriptionProvider=Provider
save=DescriptionRepository.save
def paused(self,*args):
    accepted=save(self,*args)
    if accepted and os.environ['PROBE_PAUSE']=='1': time.sleep(120)
    return accepted
DescriptionRepository.save=paused
celery_app.conf.broker_transport_options={**celery_app.conf.broker_transport_options,'global_keyprefix':os.environ['PROBE_PREFIX']}
celery_app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL',
    '--without-gossip','--without-mingle','--without-heartbeat','--queues='+os.environ['PROBE_QUEUE'],
    '--hostname='+os.environ['PROBE_QUEUE']])
'''


@pytest.mark.integration
@pytest.mark.worker_integration
def test_killed_last_frame_worker_resumes_without_repeat_model_call_or_duplicate_handoff(ingestion):
    if os.getenv('TEST_REAL_WORKER')!='1': pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO')
    repo,service,principal,project,actor=ingestion
    repo.settings=replace(repo.settings,s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT','9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER','tutorial'),s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts=S3ArtifactStore(repo.settings)
    _,publication=long_gallery(ingestion,text='user_id',count=1)
    item=queue(ingestion,publication)
    broker=os.environ['TEST_REDIS_URL'];prefix='description-probe-'+uuid4().hex+':';name='description-'+uuid4().hex
    redis=Redis.from_url(broker);redis.ping();client=Celery('description_probe',broker=broker)
    client.conf.broker_transport_options={'global_keyprefix':prefix,'socket_connect_timeout':3,'socket_timeout':5}
    workers=[]
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'APP_ENV':'test','DATABASE_URL':repo.store.database_url,
        'S3_ENDPOINT':repo.settings.s3_endpoint,'S3_ACCESS_KEY':repo.settings.s3_access_key,'S3_SECRET_KEY':repo.settings.s3_secret_key,
        'CELERY_BROKER_URL':broker,'AUTH_MODE':'development','DEVELOPMENT_AUTH_TOKEN':'fixture-development-token',
        'EMBEDDING_PROVIDER':'hash','ANSWER_PROVIDER':'extractive','FRAME_DESCRIPTIONS_ENABLED':'true','VISION_MODEL_DIGEST':'a'*64,
        'PROBE_PREFIX':prefix,'PROBE_QUEUE':name}
    def start(pause):
        worker=subprocess.Popen([sys.executable,'-c',WORKER_CODE],env={**env,'PROBE_PAUSE':'1' if pause else '0'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        workers.append(worker);return worker
    def publish(row):
        assert row['job_type']=='visual_describe'
        client.send_task('tutorial.describe_frames',args=[row['tenant_id'],str(row['project_id']),str(row['source_id']),str(row['job_id']),row['generation']],queue=name,expires=60)
    try:
        with repo.store._connect() as connection:
            connection.execute('CREATE TABLE probe_description_calls(digest text)')
            connection.execute('UPDATE outbox_events SET sent_at=now() WHERE job_id<>%s',(item.job.id,))
        first=start(True);assert dispatch_once(repo,publish)==1
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            state=repo.get_job(principal.tenant_id,project.id,item.job.id)
            if state.processed_segments==1: break
            assert first.poll() is None and state.status!='failed';time.sleep(.1)
        else: raise AssertionError('Owned description worker did not save its frame')
        assert DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor).items==[]
        first.kill();first.wait(timeout=5)
        with repo.store._connect() as connection:
            connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(item.job.id,))
        assert repo.recover_leases()==1;make_due(repo,item)
        second=start(False);assert dispatch_once(repo,publish)==1
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            state=repo.get_job(principal.tenant_id,project.id,item.job.id)
            if state.status=='succeeded': break
            assert second.poll() is None and state.status!='failed';time.sleep(.1)
        else: raise AssertionError('Replacement description worker did not publish')
        view=DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor)
        assert view.origin and view.index_job.status=='pending' and state.delivery_count==2
        with repo.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM probe_description_calls').fetchone()['n']==1
            assert connection.execute('SELECT count(*) AS n FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchone()['n']==1
            assert connection.execute('SELECT count(*) AS n FROM visual_index_runs WHERE description_job_id=%s',(item.job.id,)).fetchone()['n']==1
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try: worker.wait(timeout=5)
                except subprocess.TimeoutExpired: worker.kill();worker.wait(timeout=5)
        service.delete_project(principal,project.id)
        while cleanup_once(repo): pass
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket,Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
        keys=list(redis.scan_iter(match=prefix+'*'))
        if keys: redis.delete(*keys)
        client.close()
