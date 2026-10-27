from dataclasses import replace
from uuid import UUID, uuid4
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.jobs.dispatch import cleanup_once
from app.jobs.visual_indexing import index_visual
from app.sources.contracts import Registration
from app.sources.video import retire_unusable_video
from conftest import MappingAuthenticator, auth_headers
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import process, provider
from test_visual_gallery_integration import deliver
from test_visual_service import content

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def video_http(ingestion):
    repo = ingestion[0]
    app = create_app(settings=replace(repo.settings, video_upload_enabled=True), store=repo.store,
                     authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        project = (await client.post('/api/v1/projects', headers=auth_headers(), json={'title': 'Video boundary'})).json()
        yield client, '/api/v1/projects/' + project['id']


def multipart(*, data=None, filename='owned.mp4', mime='video/mp4', **changes):
    fields = dict(authorization_mode='owner_upload', language='en', idempotency_key='video-http-fixture', retention_acknowledged='accepted')
    fields.update(changes)
    return [('file', (filename, content() if data is None else data, mime)), *[(k, (None, v)) for k, v in fields.items() if v is not None]]


async def test_video_capability_is_fixed_authenticated_and_default_closed(video_http, ingestion):
    client, _ = video_http
    endpoint = '/api/v1/ingestion/video-capabilities'
    assert (await client.get(endpoint)).status_code == 401
    response = await client.get(endpoint, headers=auth_headers())
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == dict(enabled=True, max_bytes=100_000_000, max_duration_seconds=600, encoding='h264-avc1-yuv420p',
        max_width=1920, max_height=1080, max_fps=60, max_selected_frames=20, languages=['en', 'tr', 'en+tr'], processing_ttl_seconds=3600)
    assert not (await client.get('/api/v1/ingestion/capabilities', headers=auth_headers())).json()['enabled']
    repo = ingestion[0]
    app = create_app(settings=repo.settings, store=repo.store, authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as disabled:
        assert not (await disabled.get(endpoint, headers=auth_headers())).json()['enabled']
        result = await disabled.post('/sources/video', headers=auth_headers(), content=b'not read')
        assert result.status_code == 503 and result.json()['code'] == 'video_upload_disabled'


@pytest.mark.parametrize('patch', [dict(authorization_mode=None), dict(authorization_mode='unlicensed'), dict(language='auto'),
    dict(language=None), dict(retention_acknowledged=None), dict(retention_acknowledged='no'), dict(idempotency_key='x'),
    dict(playlist_item_id=str(uuid4())), dict(url='https://evil.example'), dict(data=b'bad'), dict(data=b''),
    dict(filename='audio.wav'), dict(filename='bad.mp4.exe'), dict(mime='audio/wav')])
async def test_invalid_video_never_adopts_a_source_or_object(video_http, ingestion, patch):
    client, path = video_http
    result = await client.post(path + '/sources/video', headers=auth_headers(), files=multipart(**patch))
    assert result.status_code in {413, 422}
    assert not ingestion[0].artifacts.objects
    assert (await client.get(path + '/sources', headers=auth_headers())).json()['items'] == []


async def test_video_auth_project_scope_duplicates_archive_and_old_upload_boundary(video_http, ingestion):
    client, path = video_http
    endpoint = path + '/sources/video'
    assert (await client.post(endpoint, files=multipart())).status_code == 401
    assert (await client.post(endpoint, headers=auth_headers('tenant-b'), files=multipart())).status_code == 404
    assert (await client.post(endpoint, headers=auth_headers(), files=multipart() + [('language', (None, 'tr'))])).status_code == 422
    assert (await client.post(path + '/sources/uploads', headers=auth_headers(), files=multipart())).status_code == 422
    await client.post(path + '/archive', headers=auth_headers())
    assert (await client.post(endpoint, headers=auth_headers(), files=multipart())).status_code == 409
    assert not ingestion[0].artifacts.objects


async def test_actual_file_bytes_are_checked_separately_from_multipart_wire(video_http, ingestion, monkeypatch):
    client, path = video_http
    monkeypatch.setattr('app.main.MAX_VIDEO_BYTES', 10)
    result = await client.post(path + '/sources/video', headers=auth_headers(), files=multipart())
    assert result.status_code == 413 and result.json()['code'] == 'video_too_large'
    assert not ingestion[0].artifacts.objects


async def test_video_api_queues_full_workflow_receipt_replay_and_cleanup_projection(video_http, ingestion, provider):
    client, path = video_http
    repo = ingestion[0]
    endpoint = path + '/sources/video'
    response = await client.post(endpoint, headers=auth_headers(), files=multipart())
    assert response.status_code == 202 and response.headers['cache-control'] == 'no-store'
    item = Registration.model_validate(response.json())
    tenant, project, source, job = item.source.tenant_id, item.source.project_id, item.source.id, item.job.id
    assert item.source.video_retention.status == 'temporary' and item.source.audio_retention is None and not provider.calls
    replay = await client.post(endpoint, headers=auth_headers(), files=multipart())
    assert replay.json()['deduplicated'] and replay.json()['job']['id'] == str(job)
    assert (await client.post(endpoint, headers=auth_headers(), files=multipart(language='tr'))).status_code == 409
    assert process(repo, item)
    current = repo.get_source(tenant, project, source)
    assert current.job.job_type == 'visual_publish' and current.video_retention.status == 'cleanup_pending'
    pub = Registration(source=current, job=current.job)
    assert not deliver(repo, pub); make_due(repo, pub); assert deliver(repo, pub)
    current = repo.get_source(tenant, project, source)
    assert index_visual(repo, tenant, project, source, current.job.id, current.generation)
    repo.artifacts.fail_delete = True
    with repo.store._connect() as connection:
        connection.execute("""UPDATE artifact_cleanup SET attempt_count=5,available_at=now()-interval '1 minute'
            WHERE tenant_id=%s AND project_id=%s AND id=(SELECT cleanup_id FROM video_inputs
            WHERE tenant_id=%s AND project_id=%s AND source_id=%s)""", (tenant, project, tenant, project, source))
    assert cleanup_once(repo) == 0
    inventory = (await client.get(path + '/sources', headers=auth_headers())).json()['items'][0]
    assert inventory['status'] == 'ready' and inventory['video_retention']['status'] == 'cleanup_failed'
    assert inventory['video_retention']['deleted_at'] is None
    assert 'object_key' not in str(inventory) and 'input_sha256' not in str(inventory)
    cleanup = inventory['video_retention']['cleanup_id']
    foreign = (await client.post('/api/v1/projects', headers=auth_headers(), json={'title': 'Other scope'})).json()['id']
    assert (await client.get(f'/api/v1/projects/{foreign}/cleanup/{cleanup}', headers=auth_headers())).status_code == 404
    assert (await client.post(path + f'/cleanup/{cleanup}/retry', headers=auth_headers('tenant-b'))).status_code == 404
    assert (await client.post(path + f'/cleanup/{cleanup}/retry', headers=auth_headers())).status_code == 200
    repo.artifacts.fail_delete = False
    assert cleanup_once(repo) == 1
    while cleanup_once(repo): pass
    current = (await client.get(path + f'/sources/{source}', headers=auth_headers())).json()
    assert current['video_retention']['status'] == 'deleted' and current['video_retention']['deleted_at']
    replay = (await client.post(endpoint, headers=auth_headers(), files=multipart())).json()
    assert replay['job']['id'] == str(job) and replay['source']['generation'] == 3
    assert (await client.delete(path + f'/sources/{source}', headers=auth_headers())).status_code == 202
    while cleanup_once(repo): pass
    assert not repo.artifacts.objects


async def test_expiry_is_not_deletion_and_cancelled_original_needs_reupload(video_http, ingestion):
    client, path = video_http
    repo = ingestion[0]
    item = (await client.post(path + '/sources/video', headers=auth_headers(), files=multipart())).json()
    source = item['source']['id']
    with repo.store._connect() as connection:
        connection.execute("UPDATE video_inputs SET expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s",
                           (item['source']['tenant_id'], UUID(item['source']['project_id'])))
    state = (await client.get(path + f'/sources/{source}', headers=auth_headers())).json()['video_retention']
    assert state['status'] == 'expired' and state['deleted_at'] is None and state['cleanup_id'] is None
    assert retire_unusable_video(repo) == 1
    assert (await client.post(path + f'/sources/{source}/retry', headers=auth_headers(), json={'idempotency_key':'retired-video-retry'})).status_code == 409
    while cleanup_once(repo): pass
    assert not repo.artifacts.objects
