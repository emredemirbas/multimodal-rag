"""WAV/playlist relationships and mixed queue leases; inference here is a fixture."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import pytest

from app.main import create_app
from app.models import AuthorizationMode, ProjectCreate
from app.sources.adapters import YouTubeMetadataProvider
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from conftest import MappingAuthenticator, auth_headers
from test_audio_upload_integration import multipart
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion, run
from test_media_integration import cleanup_all, media, process
from test_playlists_integration import playlist, provider_items, upload
from test_postgres_integration import isolated_postgres_url
from test_wav import wav_bytes

pytestmark = pytest.mark.integration


def audio(playlist, media, index=0, key='linked-audio-key', frames=16_000):
    fixture, _, items = playlist
    _, _, principal, project, actor = fixture
    return media[0].register(principal.tenant_id, project.id, actor, filename='owned.wav', content=wav_bytes(frames),
        rights=AuthorizationMode.OWNER_UPLOAD, language='en', idempotency_key=key,
        playlist_item_id=items[index].id if index is not None else None)


def claim(repo, receipt):
    return repo.claim_job(receipt.source.tenant_id, receipt.source.project_id, receipt.source.id,
                          receipt.job.id, receipt.job.generation, job_types=('asr', 'transcript'))


def test_concurrent_audio_binding_replay_busy_handoff_replacement_and_origin(playlist, media):
    fixture, root, items = playlist
    repo, service, principal, project, actor = fixture
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: audio(playlist, media), range(2)))
    result = receipts[0]
    assert sorted(r.deduplicated for r in receipts) == [False, True]
    assert receipts[0].source.id == receipts[1].source.id and len(repo.artifacts.objects) == 1
    assert result.source.parent_playlist_source_id == root.source.id
    assert result.source.metadata == {'input_kind': 'audio', 'machine_generated': True, 'requested_language': 'en',
        'playlist_item_id': str(items[0].id), 'playlist_generation': 1, 'video_id': items[0].video_id, 'alignment': 'user_asserted'}
    with pytest.raises(SourceError) as error: audio(playlist, media, index=1)
    assert error.value.code == 'idempotency_conflict'
    for register in (lambda: audio(playlist, media, key='another-audio-key'), lambda: upload(fixture, items[0])):
        with pytest.raises(SourceError) as error: register()
        assert error.value.code == 'playlist_item_busy'
    assert process(repo, result)
    generated = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert generated.kind == 'transcript' and generated.job.id != result.job.id
    # Success of ASR is not terminal for a lesson while its indexing job is pending.
    with pytest.raises(SourceError) as error: audio(playlist, media, key='index-pending-key')
    assert error.value.code == 'playlist_item_busy'
    assert run(repo, result.model_copy(update={'job': generated.job}))
    citation = service.ask(principal, project.id, 'What is GET /health?', [result.source.id]).citations[0]
    replacement = upload(fixture, items[0])
    assert run(repo, replacement)
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[0].transcript_source_id == replacement.source.id
    old = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert old.asr_origin.job_id == result.job.id and old.metadata['video_id'] == items[0].video_id
    reindex = repo.command(principal.tenant_id, project.id, old.id, actor, 'reprocess', 'linked-vtt-reindex')
    assert run(repo, reindex) and len(media[1].calls) == 1
    assert service.ask(principal, project.id, 'What is GET /health?', [old.id]).citations[0].asr_origin == citation.asr_origin
    cleanup_all(repo)
    assert all(not key.endswith('/input.wav') for key in repo.artifacts.objects)


def test_standalone_audio_hash_and_old_five_field_replay_are_unchanged(playlist, media):
    fixture, _, _ = playlist
    repo, _, principal, project, _ = fixture
    result = audio(playlist, media, index=None)
    expected = hashlib.sha256(json.dumps(['audio-asr-v1', 'owned.wav', hashlib.sha256(wav_bytes()).hexdigest(), 'owner_upload', 'en']).encode()).hexdigest()
    with repo.store._connect() as connection:
        saved = connection.execute('SELECT request_sha256 FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s',
            (principal.tenant_id, project.id, result.source.id)).fetchone()
    assert saved['request_sha256'] == expected and result.source.parent_playlist_source_id is None
    assert audio(playlist, media, index=None).deduplicated
    with pytest.raises(SourceError) as error: audio(playlist, media)
    assert error.value.code == 'idempotency_conflict'


def test_concurrent_mixed_claims_share_the_same_two_playlist_leases(playlist, media):
    fixture, _, items = playlist
    repo, _, principal, project, _ = fixture
    jobs = [audio(playlist, media, index=i, key=f'mixed-audio-{i}') if i % 2 == 0 else upload(fixture, item)
            for i, item in enumerate(items)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        claims = list(pool.map(lambda receipt: claim(repo, receipt), jobs))
    assert sum(value is not None for value in claims) == 2
    assert 'tutorial_playlist_jobs_waiting_capacity 8' in repo.render_metrics()
    for result, owned in zip(jobs, claims):
        if owned is None:
            job = repo.get_job(principal.tenant_id, project.id, result.job.id)
            assert job.stage == 'waiting_capacity' and job.attempt_count == job.delivery_count == 0
            with repo.store._connect() as connection:
                assert connection.execute('SELECT sent_at FROM outbox_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                    (principal.tenant_id, project.id, job.id)).fetchone()['sent_at'] is None
    assert claim(repo, audio(playlist, media, index=None, key='not-a-playlist-slot')) is not None


def test_asr_and_index_slots_resume_and_asr_continuation_keeps_its_attempt(playlist, media):
    fixture, _, items = playlist
    repo, _, principal, project, actor = fixture
    speech = audio(playlist, media, frames=31 * 16_000)
    assert not process(repo, speech)  # A real committed first window, not a forged continuation.
    assert len(media[1].calls) == 1
    text = upload(fixture, items[1])
    waiting_audio = audio(playlist, media, index=2, key='waiting-audio-key')
    waiting_text = upload(fixture, items[3])
    assert claim(repo, waiting_audio)['job_type'] == 'asr' and claim(repo, text)['job_type'] == 'transcript'
    make_due(repo, speech)
    assert not process(repo, speech) and claim(repo, waiting_text) is None
    assert len(media[1].calls) == 1
    assert repo.get_job(principal.tenant_id, project.id, speech.job.id).attempt_count == 1
    assert repo.get_job(principal.tenant_id, project.id, waiting_text.job.id).attempt_count == 0
    repo.command(principal.tenant_id, project.id, text.source.id, actor, 'cancel', 'cancel-index-slot')
    make_due(repo, speech)
    assert process(repo, speech) and len(media[1].calls) == 2
    assert repo.get_job(principal.tenant_id, project.id, speech.job.id).attempt_count == 1
    generated = repo.get_source(principal.tenant_id, project.id, speech.source.id)
    index = speech.model_copy(update={'job': generated.job})
    make_due(repo, waiting_text)
    assert claim(repo, waiting_text)['job_type'] == 'transcript'
    assert claim(repo, index) is None  # Handoff cannot bypass the same combined cap.
    assert repo.get_job(principal.tenant_id, project.id, index.job.id).attempt_count == 0
    repo.command(principal.tenant_id, project.id, waiting_audio.source.id, actor, 'cancel', 'free-handoff-slot')
    make_due(repo, index)
    assert run(repo, index) and len(media[1].calls) == 2


def test_refresh_preserves_audio_identity_but_not_changed_video_and_stale_replay_is_safe(playlist, media, monkeypatch):
    fixture, root, items = playlist
    repo, _, principal, project, actor = fixture
    result = audio(playlist, media)
    data = provider_items()
    for item in data: item['snippet']['position'] = 9 - item['snippet']['position']
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': data})
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'audio-reorder-snapshot')
    assert run(repo, refresh)
    current = repo.list_sources(principal.tenant_id, project.id).playlist_items
    assert current[-1].transcript_source_id == result.source.id and current[-1].id != items[0].id
    assert audio(playlist, media).deduplicated  # Same original key can recover accepted work.
    with pytest.raises(ProjectNotFoundError): audio(playlist, media, key='stale-new-upload')
    data[-1]['contentDetails']['videoId'] = 'changed0000'
    refresh = repo.command(principal.tenant_id, project.id, root.source.id, actor, 'reprocess', 'audio-changed-video')
    assert run(repo, refresh)
    assert repo.list_sources(principal.tenant_id, project.id).playlist_items[-1].transcript_source_id is None
    assert repo.get_source(principal.tenant_id, project.id, result.source.id).metadata['video_id'] == items[0].video_id


def test_metadata_deletion_keeps_independent_audio_then_source_and_project_cleanup(playlist, media):
    fixture, root, _ = playlist
    repo, service, principal, project, actor = fixture
    result = audio(playlist, media)
    repo.delete_source(principal.tenant_id, project.id, root.source.id, actor)
    cleanup_all(repo)
    assert len(repo.artifacts.objects) == 1
    assert repo.get_source(principal.tenant_id, project.id, result.source.id).parent_playlist_source_id is None
    assert audio(playlist, media).deduplicated
    assert process(repo, result)
    generated = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert run(repo, result.model_copy(update={'job': generated.job}))
    cleanup_all(repo)
    repo.delete_source(principal.tenant_id, project.id, result.source.id, actor)
    cleanup_all(repo)
    assert not repo.artifacts.objects
    audio(playlist, media, index=None, key='project-delete-independent-audio')
    service.delete_project(principal, project.id)
    cleanup_all(repo)
    assert not repo.artifacts.objects


def test_post_put_revocation_does_not_bind_or_adopt_audio_and_orphan_is_cleaned(playlist, media):
    fixture, _, items = playlist
    repo, _, principal, project, actor = fixture
    def revoke():
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    repo.artifacts.after_put = revoke
    with pytest.raises(ProjectNotFoundError): audio(playlist, media)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT transcript_source_id FROM playlist_items WHERE tenant_id=%s AND project_id=%s AND id=%s',
            (principal.tenant_id, project.id, items[0].id)).fetchone()['transcript_source_id'] is None
        assert connection.execute('SELECT count(*) AS n FROM sources WHERE tenant_id=%s AND project_id=%s',
            (principal.tenant_id, project.id)).fetchone()['n'] == 1
    cleanup_all(repo)
    assert not repo.artifacts.objects


@pytest.mark.anyio
async def test_audio_playlist_http_scope_optional_duplicate_malformed_and_busy(playlist, media):
    fixture, _, items = playlist
    repo, service, principal, project, _ = fixture
    other = service.create_project(principal, ProjectCreate(title='Other audio project'))
    class FixtureAuthenticator(MappingAuthenticator):
        def authenticate(self, headers):
            if headers.get('authorization') == auth_headers()['Authorization']:
                return principal
            return super().authenticate(headers)
    app = create_app(settings=replace(repo.settings, audio_upload_enabled=True), store=repo.store,
        artifacts=repo.artifacts, authenticator=FixtureAuthenticator())
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = f'/api/v1/projects/{project.id}/sources/audio'
        data = lambda **changes: multipart(playlist_item_id=str(items[0].id), **changes)
        assert (await client.post(path, headers=auth_headers(), files=multipart(playlist_item_id='invalid'))).status_code == 422
        assert (await client.post(path, headers=auth_headers(), files=data() + [('playlist_item_id', (None, str(items[1].id)))])).status_code == 422
        assert (await client.post(path, headers=auth_headers('tenant-b'), files=data())).status_code == 404
        assert (await client.post(f'/api/v1/projects/{other.id}/sources/audio', headers=auth_headers(), files=data())).status_code == 404
        assert (await client.post(path, headers=auth_headers(), files=multipart(playlist_item_id=str(uuid4())))).status_code == 404
        assert not repo.artifacts.objects
        response = await client.post(path, headers=auth_headers(), files=data())
        assert response.status_code == 202 and response.json()['source']['metadata']['alignment'] == 'user_asserted'
        assert (await client.post(path, headers=auth_headers(), files=data())).json()['deduplicated']
        assert (await client.post(path, headers=auth_headers(), files=data(key='busy-linked-audio'))).status_code == 409
        assert (await client.get(f'/api/v1/projects/{project.id}/sources', headers=auth_headers())).json()['playlist_items'][0]['transcript_source_id'] == response.json()['source']['id']
