from dataclasses import replace
from httpx import ASGITransport, AsyncClient
import pytest

from app.main import create_app
from app.jobs.media_processing import process_audio
from app.sources.contracts import Registration
from conftest import MappingAuthenticator, auth_headers
from test_ingestion_integration import ingestion, run
from test_media_integration import cleanup_all, media
from test_postgres_integration import isolated_postgres_url
from test_wav import wav_bytes

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def audio_http(ingestion):
    repo = ingestion[0]
    app = create_app(settings=replace(repo.settings, audio_upload_enabled=True), store=repo.store,
                     authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        project = (await client.post('/api/v1/projects', headers=auth_headers(), json={'title': 'Audio boundary'})).json()
        yield client, '/api/v1/projects/' + project['id']


def multipart(*, content=None, filename='owned.wav', mime='audio/wav', key='audio-http-key', **changes):
    fields = {'authorization_mode': 'owner_upload', 'language': 'en', 'idempotency_key': key, 'retention_acknowledged': 'accepted'}
    fields.update(changes)
    return [('file', (filename, wav_bytes(16_000) if content is None else content, mime)),
            *[(name, (None, value)) for name, value in fields.items() if value is not None]]


async def test_capability_is_authenticated_bounded_and_configured_not_model_health(audio_http, ingestion):
    client, _ = audio_http
    assert (await client.get('/api/v1/ingestion/capabilities')).status_code == 401
    response = await client.get('/api/v1/ingestion/capabilities', headers=auth_headers())
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {'enabled': True, 'max_bytes': 20_000_000, 'max_duration_seconds': 600,
                               'encoding': 'pcm-s16le-16000-mono', 'processing_ttl_seconds': 3600}
    repo = ingestion[0]
    app = create_app(settings=repo.settings, store=repo.store, authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as disabled:
        assert not (await disabled.get('/api/v1/ingestion/capabilities', headers=auth_headers())).json()['enabled']
        response = await disabled.post('/api/v1/projects/00000000-0000-0000-0000-000000000000/sources/audio', headers=auth_headers(), content=b'not read')
        assert response.status_code == 503 and response.json()['code'] == 'audio_upload_disabled'
    assert not repo.artifacts.objects


@pytest.mark.parametrize('patch,code', [
    ({'authorization_mode': None}, 'validation_error'), ({'authorization_mode': 'unlicensed'}, 'validation_error'),
    ({'language': 'de'}, 'validation_error'), ({'language': None}, 'validation_error'),
    ({'retention_acknowledged': None}, 'validation_error'), ({'retention_acknowledged': 'no'}, 'validation_error'),
    ({'idempotency_key': 'x'}, 'validation_error'), ({'extra': 'url'}, 'validation_error'),
    ({'content': b'WEBVTT'}, 'invalid_wav'), ({'filename': 'video.mp4'}, 'invalid_audio_type'),
    ({'mime': 'video/mp4'}, 'invalid_audio_type'), ({'content': b''}, 'audio_too_large'),
])
async def test_invalid_audio_never_creates_original_job_or_evidence(audio_http, ingestion, patch, code):
    client, base = audio_http
    response = await client.post(base + '/sources/audio', headers=auth_headers(), files=multipart(**patch))
    assert response.status_code in {413, 422} and response.json()['code'] == code
    assert not ingestion[0].artifacts.objects
    assert (await client.get(base + '/sources', headers=auth_headers())).json()['items'] == []


@pytest.mark.parametrize('boundary,code', [('encoding', 'unsupported_wav_encoding'),
                                         ('duration', 'audio_duration_limit'), ('bytes', 'audio_too_large')])
async def test_http_validates_actual_wav_encoding_duration_and_file_bytes(audio_http, ingestion, boundary, code):
    content = (wav_bytes(rate=44_100) if boundary == 'encoding' else
               wav_bytes(600 * 16_000 + 1) if boundary == 'duration' else b'x' * 20_000_001)
    client, base = audio_http
    response = await client.post(base + '/sources/audio', headers=auth_headers(), files=multipart(content=content))
    assert response.status_code in {413, 422} and response.json()['code'] == code
    assert not ingestion[0].artifacts.objects
    assert (await client.get(base + '/sources', headers=auth_headers())).json()['items'] == []


async def test_auth_scope_duplicate_fields_archived_and_unchanged_subtitle_boundary(audio_http, ingestion):
    client, base = audio_http
    path = base + '/sources/audio'
    assert (await client.post(path, files=multipart())).status_code == 401
    assert (await client.post(path, headers=auth_headers('tenant-b'), files=multipart())).status_code == 404
    duplicate = multipart() + [('language', (None, 'tr'))]
    assert (await client.post(path, headers=auth_headers(), files=duplicate)).status_code == 422
    old = await client.post(base + '/sources/uploads', headers=auth_headers(), files=multipart())
    assert old.status_code == 422
    await client.post(base + '/archive', headers=auth_headers())
    assert (await client.post(path, headers=auth_headers(), files=multipart())).status_code == 409
    assert not ingestion[0].artifacts.objects


async def test_audio_request_keys_receipts_and_commands_are_project_scoped(audio_http, ingestion):
    client, first = audio_http
    other = (await client.post('/api/v1/projects', headers=auth_headers(), json={'title': 'Separate audio project'})).json()
    second = '/api/v1/projects/' + other['id']
    one = (await client.post(first + '/sources/audio', headers=auth_headers(), files=multipart())).json()
    two = (await client.post(second + '/sources/audio', headers=auth_headers(), files=multipart())).json()
    assert not one['deduplicated'] and not two['deduplicated']
    assert one['source']['id'] != two['source']['id'] and two['source']['project_id'] == other['id']
    assert (await client.get(second + '/sources/' + one['source']['id'], headers=auth_headers())).status_code == 404
    assert (await client.get(second + '/jobs/' + one['job']['id'], headers=auth_headers())).status_code == 404
    assert (await client.post(second + '/sources/' + one['source']['id'] + '/cancel', headers=auth_headers(),
                              json={'idempotency_key': 'foreign-project-cancel'})).status_code == 404
    assert (await client.delete(second + '/sources/' + one['source']['id'], headers=auth_headers())).status_code == 404
    assert (await client.delete(second, headers=auth_headers())).status_code == 204
    cleanup_all(ingestion[0])
    assert (await client.get(first + '/sources/' + one['source']['id'], headers=auth_headers())).status_code == 200
    assert len(ingestion[0].artifacts.objects) == 1


async def test_upload_only_enqueues_asr_then_handoff_citation_cleanup_and_reupload_rules(audio_http, ingestion, media):
    client, base = audio_http
    repo = ingestion[0]
    path = base + '/sources/audio'
    accepted = await client.post(path, headers=auth_headers(), files=multipart())
    assert accepted.status_code == 202 and accepted.headers['cache-control'] == 'no-store'
    receipt = Registration.model_validate(accepted.json())
    source, job, tenant, project = receipt.source.id, receipt.job.id, receipt.source.tenant_id, receipt.source.project_id
    assert receipt.source.kind == 'audio' and receipt.source.audio_retention.status == 'temporary'
    assert not media[1].calls  # No native inference in the API request.
    replay = await client.post(path, headers=auth_headers(), files=multipart())
    assert replay.status_code == 202 and replay.json()['deduplicated'] and replay.json()['job']['id'] == str(job)
    assert (await client.post(path, headers=auth_headers(), files=multipart(language='tr'))).status_code == 409
    assert process_audio(repo, tenant, project, source, job, 1)
    handoff = repo.get_source(tenant, project, source)
    assert handoff.job.id != job and run(repo, receipt.model_copy(update={'job': handoff.job}))
    transcript = (await client.get(base + f'/sources/{source}/transcript', headers=auth_headers())).json()
    assert transcript['asr_origin']['job_id'] == str(job) and transcript['items']
    cleanup_all(repo)
    final = (await client.get(base + f'/sources/{source}', headers=auth_headers())).json()
    assert final['audio_retention']['status'] == 'deleted' and final['asr_origin']['machine_generated']
    deleted = await client.delete(base + f'/sources/{source}', headers=auth_headers())
    assert deleted.status_code == 202
    cleanup_all(repo)
    assert not repo.artifacts.objects and (await client.get(base + f'/sources/{source}', headers=auth_headers())).status_code == 404
    # New source cancellation retires the original; retry cannot resurrect it.
    second = (await client.post(path, headers=auth_headers(), files=multipart(key='cancel-audio-http'))).json()
    cancel = base + '/sources/' + second['source']['id']
    assert (await client.post(cancel + '/cancel', headers=auth_headers(), json={'idempotency_key': 'cancel-owned-audio'})).status_code == 202
    retry = await client.post(cancel + '/retry', headers=auth_headers(), json={'idempotency_key': 'retry-owned-audio'})
    assert retry.status_code == 409 and retry.json()['code'] == 'audio_reupload_required'
    cleanup_all(repo)
    assert not repo.artifacts.objects
