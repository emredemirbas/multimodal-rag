"""Real PostgreSQL temporal inspection; fixture frames, no native/model claims."""
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.auth import AuthenticationError
from app.jobs.dispatch import cleanup_once
from app.main import create_app
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.sources.alignment import AlignmentRepository
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from app.vision.gallery import VisualGalleryRepository
from test_ingestion_integration import ingestion, register, run
from test_media_integration import media, register_audio, process
from test_postgres_integration import isolated_postgres_url
from test_visual_gallery_integration import complete, queue

pytestmark = pytest.mark.integration
VTT = 'WEBVTT\n\n00:00.000 --> 00:05.000\nFirst span user_id.\n\n00:05.000 --> 00:08.000\nSecond span request.json().\n'


def transcript(fixture, content=VTT):
    _, service, principal, project, _ = fixture
    return service.ingest_transcript(principal, project.id, TranscriptIngestRequest(filename='owned.vtt',
        authorization_mode='owner_upload', idempotency_key='align-transcript-' + uuid4().hex, content=content)).source


def pair(fixture, content=VTT):
    _, visual = complete(fixture)
    return visual.source.id, transcript(fixture, content).id


def read(fixture, visual, text, **query):
    repo, _, principal, project, actor = fixture
    return AlignmentRepository(repo).read(principal.tenant_id, project.id, actor, visual, text,
        assert_same_recording=True, **query)


def test_actual_half_open_pts_spans_not_nearest_cues_or_semantic_verification(ingestion, caplog):
    visual, text = pair(ingestion)
    caplog.set_level('INFO', logger='tutorial_workspace')
    repo, _, principal, project, actor = ingestion
    repo.artifacts.fail_get = True  # JSON inspection must not fetch media/objects.
    result = read(ingestion, visual, text)
    assert result.relationship == 'user_asserted' and result.semantics_verified is False
    assert result.gallery.generation == 2 and result.transcript.generation == 1
    assert result.matched_frames == 2
    assert [item.transcript_time_ms for item in result.items] == [0, 5000]
    assert [item.matches[0].excerpt for item in result.items] == ['First span user_id.', 'Second span request.json().']
    gap = read(ingestion, visual, text, offset_ms=8000)
    assert gap.matched_frames == 0 and all(not item.matches for item in gap.items)
    before_start = read(ingestion, visual, text, offset_ms=-1)
    assert before_start.items[0].transcript_time_ms == -1 and not before_start.items[0].matches
    assert before_start.items[1].matches[0].start_ms == 0
    assert 'timeline_alignment_read' in caplog.text and '"matched_frames": 2' in caplog.text
    assert not any(secret in caplog.text for secret in ['PRIVATE_OCR', 'user_id', 'owned.vtt', 'request.json'])
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM retrieval_runs').fetchone()['n'] == 0


def test_overlaps_and_long_legacy_text_are_bounded_flagged_and_stably_ordered(ingestion):
    content = 'WEBVTT\n\n' + '\n\n'.join(f'00:00.000 --> 00:08.000\nLegacy {i} ' + ('x ' * 2500) for i in range(7))
    visual, text = pair(ingestion, content)
    result = read(ingestion, visual, text)
    for frame in result.items:
        assert frame.matches_truncated and len(frame.matches) == 5
        assert [item.segment_id for item in frame.matches] == sorted(item.segment_id for item in frame.matches)
        assert all(len(item.excerpt) == 4000 and item.text_truncated for item in frame.matches)
    assert len(result.model_dump_json()) < 60_000


def test_both_generations_pinned_and_old_transcript_survives_reprocessing(ingestion):
    repo, _, principal, project, actor = ingestion
    _, visual = complete(ingestion)
    text = register(ingestion)
    assert run(repo, text)
    before = read(ingestion, visual.source.id, text.source.id)
    replacement = repo.command(principal.tenant_id, project.id, text.source.id, actor, 'reprocess', 'alignment-reprocess')
    assert read(ingestion, visual.source.id, text.source.id).items == before.items
    with pytest.raises(ProjectNotFoundError):
        read(ingestion, visual.source.id, text.source.id, visual_generation=2, transcript_generation=2)
    assert run(repo, replacement)
    pinned = read(ingestion, visual.source.id, text.source.id, visual_generation=2, transcript_generation=1)
    assert pinned.items == before.items and pinned.transcript.active_generation == 2
    latest = read(ingestion, visual.source.id, text.source.id)
    assert latest.transcript.generation == 2
    assert latest.items[0].matches[0].segment_id != pinned.items[0].matches[0].segment_id
    with pytest.raises(ProjectNotFoundError):
        read(ingestion, visual.source.id, text.source.id, visual_generation=1, transcript_generation=1)


def test_generated_audio_keeps_its_machine_origin_in_the_temporal_view(ingestion, media):
    repo, _, principal, project, _ = ingestion
    _, visual = complete(ingestion)
    audio = register_audio(ingestion, media, frames=16000)
    assert process(repo, audio)
    current = repo.get_source(principal.tenant_id, project.id, audio.source.id)
    assert run(repo, audio.model_copy(update={'job': current.job}))
    view = read(ingestion, visual.source.id, audio.source.id)
    assert view.transcript.asr_origin.machine_generated
    assert view.transcript.asr_origin.job_id == audio.job.id
    assert view.transcript.asr_origin.generation == 1
    assert len(media[1].calls) == 1  # Inspection never runs another ASR call.


def test_one_read_only_snapshot_does_not_mix_sources_during_concurrent_deletion(ingestion, monkeypatch):
    visual, text = pair(ingestion)
    repo, _, principal, project, actor = ingestion
    original = VisualGalleryRepository.read_snapshot
    observations = []
    def remove_after_gallery(self, connection, *args, **kwargs):
        result = original(self, connection, *args, **kwargs)
        assert connection.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on'
        assert connection.execute('SHOW transaction_isolation').fetchone()['transaction_isolation'] == 'repeatable read'
        if not observations:
            repo.delete_source(principal.tenant_id, project.id, text, actor)
            observations.append(True)
        return result
    monkeypatch.setattr(VisualGalleryRepository, 'read_snapshot', remove_after_gallery)
    assert read(ingestion, visual, text).matched_frames == 2  # Consistent pre-deletion snapshot.
    with pytest.raises(ProjectNotFoundError): read(ingestion, visual, text)


def test_no_private_gallery_or_unpublished_transcript_becomes_a_comparison(ingestion):
    repo = ingestion[0]
    _, pending = queue(ingestion)
    text = transcript(ingestion)
    with pytest.raises(SourceError, match='complete gallery'):
        read(ingestion, pending.source.id, text.id)
    # Separate fixture source is an unfinished durable subtitle upload.
    unpublished = register(ingestion)
    with pytest.raises(SourceError) as failure:
        read(ingestion, pending.source.id, unpublished.source.id)
    assert failure.value.code == 'alignment_not_ready'
    with pytest.raises(ProjectNotFoundError):
        read(ingestion, pending.source.id, unpublished.source.id, visual_generation=2, transcript_generation=1)


@pytest.mark.parametrize('query', [{'assert_same_recording': False}, {'offset_ms': True}, {'offset_ms': 600001},
    {'offset_ms': -600001}, {'visual_generation': 2}, {'transcript_generation': 1},
    {'visual_generation': 0, 'transcript_generation': 1}])
def test_bad_comparison_is_rejected_before_database_access(query):
    class NoDatabase:
        @property
        def store(self): pytest.fail('Validate comparison before reads')
    options = {'assert_same_recording': True, **query}
    with pytest.raises(SourceError): AlignmentRepository(NoDatabase()).read('tenant', uuid4(), uuid4(), uuid4(), uuid4(), **options)


def test_both_source_scopes_membership_and_archived_inspection(ingestion):
    visual, text = pair(ingestion)
    repo, service, principal, project, actor = ingestion
    other_project = service.create_project(principal, ProjectCreate(title='Another project'))
    other_text = service.ingest_transcript(principal, other_project.id, TranscriptIngestRequest(filename='other.vtt',
        content=VTT, authorization_mode='owner_upload', idempotency_key='other-transcript-alignment')).source
    for tenant, pid, user, v, t in [('foreign', project.id, actor, visual, text),
        (principal.tenant_id, other_project.id, actor, visual, other_text.id),
        (principal.tenant_id, project.id, uuid4(), visual, text),
        (principal.tenant_id, project.id, actor, visual, other_text.id),
        (principal.tenant_id, project.id, actor, text, visual)]:
        with pytest.raises((ProjectNotFoundError, SourceError)):
            AlignmentRepository(repo).read(tenant, pid, user, v, t, assert_same_recording=True)
    before = read(ingestion, visual, text)
    service.archive_project(principal, project.id)
    assert read(ingestion, visual, text) == before


@pytest.mark.parametrize('removed', ['transcript', 'visual', 'project', 'membership'])
def test_deleted_or_revoked_pair_is_no_longer_readable(ingestion, removed):
    visual, text = pair(ingestion)
    repo, service, principal, project, actor = ingestion
    assert read(ingestion, visual, text).matched_frames == 2
    if removed == 'project': service.delete_project(principal, project.id)
    elif removed == 'membership':
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    else: repo.delete_source(principal.tenant_id, project.id, text if removed == 'transcript' else visual, actor)
    with pytest.raises(ProjectNotFoundError): read(ingestion, visual, text, visual_generation=2, transcript_generation=1)
    if removed != 'membership':
        while cleanup_once(repo): pass
    if removed in {'project', 'visual'}:
        assert not any('/frame.png' in key for key in repo.artifacts.objects)


def test_auth_query_validation_no_store_and_content_free_http_logs(ingestion):
    visual, text = pair(ingestion)
    repo, _, principal, project, _ = ingestion
    class FixtureAuth:
        def authenticate(self, headers):
            if headers.get('authorization') == 'Bearer alignment-test-token': return principal
            raise AuthenticationError()
    app = create_app(settings=replace(repo.settings, store_backend='postgres'), store=repo.store,
                     artifacts=repo.artifacts, authenticator=FixtureAuth())
    path = f'/api/v1/projects/{project.id}/sources/{visual}/alignment'
    query = {'transcript_source_id': str(text), 'assert_same_recording': 'true'}
    with TestClient(app) as client:
        assert client.get(path, params=query).status_code == 401
        headers = {'Authorization': 'Bearer alignment-test-token'}
        response = client.get(path, params=query, headers=headers)
        assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'
        assert response.json()['matched_frames'] == 2
        assert not any(secret in response.text for secret in ['object_key', 'input_sha256', 'selection_manifest', 'language_data'])
        for patch in [{'assert_same_recording': 'false'}, {'assert_same_recording': '1'}, {'offset_ms': '600001'},
                      {'visual_generation': '2'}, {'unknown': 'PRIVATE_QUERY'}]:
            assert client.get(path, params={**query, **patch}, headers=headers).status_code == 422
        assert client.get(path, params=[*query.items(), ('transcript_source_id', str(text))], headers=headers).status_code == 422
        assert client.get(path, params={'transcript_source_id': str(text)}, headers=headers).status_code == 422
        failure = client.get(path, params={**query, 'transcript_source_id': str(uuid4())}, headers=headers)
        assert failure.status_code == 404 and failure.headers['cache-control'] == 'private, no-store'
        assert failure.headers['x-content-type-options'] == 'nosniff'


def test_gallery_image_manifest_verification_uses_its_own_published_generation(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    _, publication = complete(ingestion)
    gallery = VisualGalleryRepository(repo)
    frame = gallery.gallery(principal.tenant_id, project.id, publication.source.id, actor).items[0]
    original = gallery.gallery
    calls = []
    def pinned(*args, **kwargs):
        calls.append(kwargs.get('generation'))
        return original(*args, **kwargs)
    monkeypatch.setattr(gallery, 'gallery', pinned)
    assert gallery.image(principal.tenant_id, project.id, frame.id, actor).startswith(b'\x89PNG')
    assert calls == [2]
