from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from app.models import AuthenticatedPrincipal, AuthorizationMode, ProjectCreate
from app.sources.adapters import YouTubeMetadataProvider
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_ingestion_integration import TRANSCRIPT, ingestion, run
from test_postgres_integration import isolated_postgres_url

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('limit', [0, 5])
def test_invalid_playlist_slot_config_is_rejected(limit):
    from app.config import Settings
    with pytest.raises(ValueError, match='PLAYLIST_CONCURRENCY'):
        Settings(development_auth_token='test-development-token', playlist_concurrency=limit)


def provider_items(count=10):
    return [{'id': f'entry-{i}', 'contentDetails': {'videoId': f'video{i:06d}'},
             'snippet': {'title': f'Lesson {i + 1}', 'position': i}} for i in reversed(range(count))]


@pytest.fixture
def playlist(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    repo.settings = replace(repo.settings, youtube_api_key='fixture-not-a-real-key')
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': provider_items()})
    root = repo.register_metadata(principal.tenant_id, project.id, actor,
        url='https://www.youtube.com/playlist?list=PLabcdefghijk', rights=AuthorizationMode.OWNER_UPLOAD,
        idempotency_key='playlist-fixture-key')
    assert run(repo, root)
    return ingestion, root, repo.list_sources(principal.tenant_id, project.id).playlist_items


def upload(fixture, item, *, key=None, content=TRANSCRIPT):
    repo, _, principal, project, actor = fixture
    return repo.register(principal.tenant_id, project.id, actor, filename=f'lesson-{item.position}.vtt',
        content=content, rights=AuthorizationMode.AUTHORIZED_UPLOAD, idempotency_key=key or 'upload-'+uuid4().hex,
        playlist_item_id=item.id)


def claim(repo, result):
    return repo.claim_job(result.source.tenant_id, result.source.project_id, result.source.id, result.job.id, result.job.generation)


def test_ordered_snapshot_and_concurrent_upload_replay(playlist):
    fixture, root, items = playlist
    repo, service, principal, project, _ = fixture
    assert [item.position for item in items] == list(range(10))
    assert service.ask(principal, project.id, 'What is GET /health?').abstained
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(fixture, items[0], key='same-playlist-upload'), range(2)))
    assert results[0].source.id == results[1].source.id
    assert len(repo.artifacts.objects) == 1
    assert results[0].source.parent_playlist_source_id == root.source.id
    assert results[0].source.metadata['alignment'] == 'user_asserted'
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[0].transcript_source_id == results[0].source.id
    with pytest.raises(SourceError) as conflict:
        upload(fixture, items[1], key='same-playlist-upload')
    assert conflict.value.code == 'idempotency_conflict'
    with pytest.raises(SourceError) as busy:
        upload(fixture, items[0])
    assert busy.value.code == 'playlist_item_busy'
    assert len(repo.artifacts.objects) == 1


def test_concurrent_claims_wait_without_consuming_attempts_and_resume(playlist):
    fixture, _, items = playlist
    repo, _, principal, project, actor = fixture
    jobs = [upload(fixture, item) for item in items]
    with ThreadPoolExecutor(max_workers=10) as pool:
        claims = list(pool.map(lambda result: claim(repo, result), jobs))
    active = [result for result, owned in zip(jobs, claims) if owned]
    waiting = [result for result, owned in zip(jobs, claims) if not owned]
    assert len(active) == 2 and len(waiting) == 8
    assert 'tutorial_playlist_jobs_waiting_capacity 8' in repo.render_metrics()
    for result in waiting:
        job = repo.get_job(principal.tenant_id, project.id, result.job.id)
        assert job.stage == 'waiting_capacity' and job.attempt_count == 0
        with repo.store._connect() as connection:
            row = connection.execute('SELECT sent_at FROM outbox_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                (principal.tenant_id, project.id, result.job.id)).fetchone()
            assert row['sent_at'] is None
    repo.command(principal.tenant_id, project.id, active[0].source.id, actor, 'cancel', 'free-slot-cancel')
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s',
            (principal.tenant_id, project.id, waiting[0].job.id))
    resumed = claim(repo, waiting[0])
    assert resumed and resumed['attempt_count'] == 1
    assert not repo.stage(claims[jobs.index(active[0])], 'embedding', 50)


def test_ten_video_partial_failure_retry_and_corrected_replacement(playlist):
    fixture, _, items = playlist
    repo, service, principal, project, actor = fixture
    jobs = [upload(fixture, item, content=b'not a valid subtitle' if item.position == 4 else TRANSCRIPT) for item in items]
    assert sum(run(repo, job) for job in jobs) == 9
    failed = jobs[4]
    assert repo.get_job(principal.tenant_id, project.id, failed.job.id).status == 'failed'
    retry = repo.command(principal.tenant_id, project.id, failed.source.id, actor, 'retry', 'retry-single-video')
    assert not run(repo, retry)
    assert all(repo.get_job(principal.tenant_id, project.id, job.job.id).attempt_count == 1 for i, job in enumerate(jobs) if i != 4)
    corrected = upload(fixture, items[4])
    assert run(repo, corrected)
    assert repo.get_source(principal.tenant_id, project.id, failed.source.id).status == 'failed'
    listed = repo.list_sources(principal.tenant_id, project.id)
    assert listed.playlist_items[4].transcript_source_id == corrected.source.id
    assert not service.ask(principal, project.id, 'What is GET /health?', [corrected.source.id]).abstained
    assert all(repo.get_source(principal.tenant_id, project.id, item.transcript_source_id).active_generation == 1 for item in listed.playlist_items)


def test_refresh_carries_matching_identity_only_and_failed_refresh_keeps_snapshot(playlist, monkeypatch):
    fixture, root, items = playlist
    repo, service, principal, project, actor = fixture
    transcript = upload(fixture, items[0])
    assert run(repo, transcript)
    citation = service.ask(principal, project.id, 'What is GET /health?', [transcript.source.id]).citations[0]
    malformed = provider_items()
    malformed[0]['id'] = malformed[1]['id']
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': malformed})
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'bad-refresh')
    assert not run(repo, refresh)
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[0].id == items[0].id
    changed = provider_items()
    for item in changed:
        item['snippet']['position'] = 9-item['snippet']['position']
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': changed})
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'good-refresh')
    assert run(repo, refresh)
    new = repo.list_sources(principal.tenant_id, project.id).playlist_items
    assert new[-1].transcript_source_id == transcript.source.id and new[-1].generation == 3
    assert new[-1].id != items[0].id
    with pytest.raises(ProjectNotFoundError):
        upload(fixture, items[0])
    assert service.ask(principal, project.id, 'What is GET /health?', [transcript.source.id]).citations[0] == citation
    # A reused provider item whose video changed must not inherit the transcript.
    changed[-1]['contentDetails']['videoId'] = 'newvideo000'
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'changed-video-refresh')
    assert run(repo, refresh)
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[-1].transcript_source_id is None


def test_scope_and_delete_preserve_only_independent_sources(playlist):
    fixture, root, items = playlist
    repo, service, principal, project, actor = fixture
    result = upload(fixture, items[0])
    assert run(repo, result)
    other = service.create_project(principal, ProjectCreate(title='Other project'))
    outsider = AuthenticatedPrincipal(provider='test', subject='outsider', tenant_id='outsider-tenant')
    outsider_actor = repo.store.bootstrap_principal(outsider)
    for tenant, target, user in [(principal.tenant_id, other.id, actor), (outsider.tenant_id, project.id, outsider_actor)]:
        with pytest.raises(ProjectNotFoundError):
            repo.register(tenant, target, user, filename='scope.vtt', content=TRANSCRIPT,
                rights=AuthorizationMode.OWNER_UPLOAD, idempotency_key='scoped-item-upload', playlist_item_id=items[0].id)
    assert repo.list_sources(principal.tenant_id, other.id).playlist_items == []
    assert repo.claim_job(principal.tenant_id, other.id, result.source.id, result.job.id, 1) is None
    assert repo.claim_job(outsider.tenant_id, project.id, result.source.id, result.job.id, 1) is None
    repo.delete_source(principal.tenant_id, project.id, result.source.id, actor)
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[0].transcript_source_id is None
    replacement = upload(fixture, items[0])
    assert run(repo, replacement)
    repo.delete_source(principal.tenant_id, project.id, root.source.id, actor)
    assert not repo.list_sources(principal.tenant_id, project.id).playlist_items
    assert repo.get_source(principal.tenant_id, project.id, replacement.source.id).parent_playlist_source_id is None
    assert not service.ask(principal, project.id, 'What is GET /health?', [replacement.source.id]).abstained
    service.delete_project(principal, project.id)
    with repo.store._connect() as connection:
        for table in ['playlist_items', 'sources', 'processing_jobs', 'usage_events']:
            assert connection.execute(f'SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s',
                (principal.tenant_id, project.id)).fetchone()['count'] == 0


def test_repeated_video_uses_distinct_playlist_item_relationships(playlist, monkeypatch):
    fixture, root, _ = playlist
    repo, _, principal, project, actor = fixture
    data = provider_items(2)
    data[0]['contentDetails']['videoId'] = data[1]['contentDetails']['videoId']
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': data})
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'repeat-video-refresh')
    assert run(repo, refresh)
    items = repo.list_sources(principal.tenant_id, project.id).playlist_items
    assert items[0].video_id == items[1].video_id and items[0].id != items[1].id
    first, second = (upload(fixture, item) for item in items)
    linked = repo.list_sources(principal.tenant_id, project.id).playlist_items
    assert linked[0].transcript_source_id == first.source.id
    assert linked[1].transcript_source_id == second.source.id


@pytest.mark.anyio
async def test_http_upload_item_contract_and_authorization(playlist):
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.auth import DevelopmentAuthenticator
    fixture, _, items = playlist
    repo, _, principal, project, _ = fixture
    token = 'playlist-http-test-token'
    app = create_app(settings=repo.settings, store=repo.store, artifacts=repo.artifacts,
        authenticator=DevelopmentAuthenticator(token=token, subject=principal.subject, tenant_id=principal.tenant_id))
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = f'/api/v1/projects/{project.id}/sources'
        data = {'authorization_mode': 'owner_upload', 'idempotency_key': 'http-item-upload', 'playlist_item_id': str(items[0].id)}
        file = {'file': ('http.vtt', TRANSCRIPT, 'text/vtt')}
        assert (await client.post(path+'/uploads', data=data, files=file)).status_code == 401
        headers = {'Authorization': 'Bearer '+token}
        assert (await client.post(path+'/uploads', headers=headers, data={**data, 'playlist_item_id': 'not-a-uuid'}, files=file)).status_code == 422
        assert (await client.post(path+'/uploads', headers=headers, data={**data, 'playlist_item_id': str(uuid4())}, files=file)).status_code == 404
        response = await client.post(path+'/uploads', headers=headers, data=data, files=file)
        assert response.status_code == 202
        listed = (await client.get(path, headers=headers)).json()
        assert listed['playlist_items'][0]['transcript_source_id'] == response.json()['source']['id']


@pytest.mark.worker_integration
def test_actual_three_workers_obey_two_slots_and_resume_ten_videos(playlist):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import time
    from celery import Celery
    from redis import Redis
    from app.artifacts.storage import S3ArtifactStore
    from app.jobs.dispatch import dispatch_once
    from test_worker_process_integration import WORKER_CODE

    if os.getenv('TEST_REAL_WORKER') != '1':
        pytest.skip('Set TEST_REAL_WORKER=1 with Redis and MinIO available')
    fixture, _, items = playlist
    repo, _, principal, project, _ = fixture
    settings = replace(repo.settings, s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
        s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    repo.artifacts = S3ArtifactStore(settings)
    broker = os.getenv('TEST_REDIS_URL', f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6380')}/0")
    prefix, queue = 'playlist-probe-'+uuid4().hex+':', 'probe-'+uuid4().hex
    client = Celery('playlist_probe', broker=broker)
    client.conf.broker_transport_options = {'global_keyprefix': prefix, 'socket_connect_timeout': 3, 'socket_timeout': 5}
    redis = Redis.from_url(broker)
    redis.ping()
    assert not list(redis.scan_iter(match=prefix+'*'))
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'APP_ENV': 'test',
        'DATABASE_URL': repo.store.database_url, 'S3_ENDPOINT': settings.s3_endpoint,
        'S3_ACCESS_KEY': settings.s3_access_key, 'S3_SECRET_KEY': settings.s3_secret_key,
        'CELERY_BROKER_URL': broker, 'AUTH_MODE': 'development', 'DEVELOPMENT_AUTH_TOKEN': 'probe-development-token',
        'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive',
        'PROBE_PREFIX': prefix, 'PROBE_QUEUE': queue, 'PROBE_PAUSE': '0', 'PROBE_DELAY': '1', 'PLAYLIST_CONCURRENCY': '2'}
    workers = []

    def publish(row):
        client.send_task('tutorial.process_transcript', args=[row['tenant_id'], str(row['project_id']),
            str(row['source_id']), str(row['job_id']), row['generation']], queue=queue, expires=60)

    try:
        jobs = [upload(fixture, item, content=b'invalid subtitle' if item.position == 4 else TRANSCRIPT) for item in items]
        for index in range(3):
            workers.append(subprocess.Popen([sys.executable, '-c', WORKER_CODE], env={**env, 'PROBE_HOST_SUFFIX': '-'+str(index)},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.monotonic()+45
        saw_waiting, max_active = False, 0
        while time.monotonic() < deadline:
            dispatch_once(repo, publish)
            with repo.store._connect() as connection:
                states = connection.execute('SELECT status,stage FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND job_type=\'transcript\'',
                    (principal.tenant_id, project.id)).fetchall()
            active = sum(row['status'] == 'running' for row in states)
            max_active = max(max_active, active)
            assert active <= 2
            saw_waiting |= any(row['stage'] == 'waiting_capacity' for row in states)
            if len(states) == 10 and all(row['status'] in {'succeeded', 'failed'} for row in states):
                break
            time.sleep(.1)
        else:
            raise AssertionError('Test-owned playlist workers did not finish')
        assert saw_waiting and max_active == 2
        assert sum(row['status'] == 'succeeded' for row in states) == 9
        assert repo.get_job(principal.tenant_id, project.id, jobs[4].job.id).status == 'failed'
        # Correct only the failed video's upload, preserving the other nine results.
        corrected = upload(fixture, items[4])
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            dispatch_once(repo, publish)
            if repo.get_job(principal.tenant_id, project.id, corrected.job.id).status == 'succeeded':
                break
            time.sleep(.1)
        else:
            raise AssertionError('Test-owned replacement did not finish')
        assert all(repo.get_job(principal.tenant_id, project.id, job.job.id).attempt_count == 1 for i, job in enumerate(jobs) if i != 4)
        assert repo.get_job(principal.tenant_id, project.id, corrected.job.id).attempt_count == 1
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
        repo.artifacts.delete_prefix(f'{principal.tenant_id}/{project.id}/')
        keys = list(redis.scan_iter(match=prefix+'*'))
        if keys:
            redis.delete(*keys)
        client.close()
