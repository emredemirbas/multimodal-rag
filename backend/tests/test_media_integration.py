"""Private backend lifecycle; fake inference is not native ASR quality evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from uuid import UUID, uuid4

import pytest
import psycopg

from app.asr.wav import SAMPLE_RATE, SLICE_FRAMES
from app.jobs.dispatch import cleanup_once, dispatch_once
from app.jobs.media_processing import process_audio
from app.jobs.queue import delivery_route
from app.models import AuthenticatedPrincipal, AuthorizationMode, ProjectCreate
from app.sources.contracts import SourceError
from app.sources.media import MediaRepository, retire_unusable_audio
from app.store import ProjectNotFoundError
from test_asr_transcript import speech
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion, run
from test_postgres_integration import isolated_postgres_url
from test_wav import wav_bytes

pytestmark = pytest.mark.integration


class FixtureSpeech:
    def __init__(self):
        self.calls, self.error, self.after_call = [], None, None

    def transcribe(self, pcm, language):
        self.calls.append(hashlib.sha256(pcm).hexdigest())
        if self.after_call:
            self.after_call()
        if self.error:
            raise self.error
        return speech(len(pcm) // 2, language=language)


@pytest.fixture
def media(ingestion, monkeypatch):
    repo = ingestion[0]
    provider = FixtureSpeech()
    monkeypatch.setattr('app.jobs.media_processing.build_transcription_provider', lambda _: provider)
    return MediaRepository(repo), provider


def register_audio(ingestion, media, *, key='owned-audio-upload', frames=SLICE_FRAMES + SAMPLE_RATE, language='en'):
    _, _, principal, project, actor = ingestion
    return media[0].register(principal.tenant_id, project.id, actor, filename='owned.wav', content=wav_bytes(frames),
                            rights=AuthorizationMode.OWNER_UPLOAD, language=language, idempotency_key=key)


def process(repo, result):
    return process_audio(repo, result.source.tenant_id, result.source.project_id, result.source.id, result.job.id, result.job.generation)


def cleanup_all(repo):
    for _ in range(20):
        if not cleanup_once(repo):
            break


def test_registration_concurrency_idempotency_and_correct_queue_routing(ingestion, media):
    repo, _, principal, project, _ = ingestion
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register_audio(ingestion, media), range(2)))
    assert results[0].source.id == results[1].source.id and sorted(r.deduplicated for r in results) == [False, True]
    assert len(repo.artifacts.objects) == 1
    with pytest.raises(SourceError) as error: register_audio(ingestion, media, language='tr')
    assert error.value.code == 'idempotency_conflict'
    rows = []
    assert dispatch_once(repo, rows.append) == 1
    assert rows[0]['job_type'] == 'asr' and delivery_route(rows[0]['job_type']) == ('tutorial.process_audio', 'media')
    assert rows[0]['tenant_id'] == principal.tenant_id and rows[0]['project_id'] == project.id
    with repo.store._connect() as connection:
        row = connection.execute('SELECT * FROM audio_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, results[0].job.id)).fetchone()
        assert row['cleanup_id'] is None and row['deleted_at'] is None
        assert row['input_frames'] == SLICE_FRAMES + SAMPLE_RATE and row['requested_language'] == 'en'
        assert connection.execute('SELECT count(*) AS n FROM source_artifacts WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0


def test_bounded_continuation_atomic_handoff_raw_cleanup_reindex_and_provenance(ingestion, media):
    repo, service, principal, project, actor = ingestion
    result = register_audio(ingestion, media)
    assert not process(repo, result)
    halfway = repo.get_job(principal.tenant_id, project.id, result.job.id)
    assert halfway.stage == 'waiting_asr_continuation' and halfway.attempt_count == 1 and halfway.delivery_count == 1
    assert repo.get_source(principal.tenant_id, project.id, result.source.id).active_generation is None
    make_due(repo, result)
    assert process(repo, result)
    assert len(media[1].calls) == 2 and not process(repo, result)
    transcribed = repo.get_job(principal.tenant_id, project.id, result.job.id)
    assert transcribed.status == 'succeeded' and transcribed.attempt_count == 1 and transcribed.delivery_count == 2
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert source.kind == 'transcript' and source.filename == 'owned.vtt' and source.metadata['machine_generated']
    assert source.active_generation is None and source.job.id != result.job.id
    with repo.store._connect() as connection:
        scope = principal.tenant_id, project.id, result.source.id
        artifact = connection.execute('SELECT * FROM source_artifacts WHERE tenant_id=%s AND project_id=%s AND source_id=%s', scope).fetchone()
        assert artifact['asr_job_id'] == result.job.id
        usage = connection.execute('SELECT * FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, result.job.id)).fetchone()
        assert usage['input_audio_frames'] == 496000 and usage['input_tokens'] is None and usage['billed_usd'] == 0
        assert usage['embedding_space'] is None and usage['provider'] == 'faster-whisper-local' and usage['duration_ms'] == 34
    cleanup_all(repo)
    assert list(repo.artifacts.objects) == [artifact['object_key']]
    with repo.store._connect() as connection:
        original = connection.execute('SELECT * FROM audio_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, result.job.id)).fetchone()
        assert original['deleted_at'] is not None
    assert repo.get_cleanup(principal.tenant_id, project.id, original['cleanup_id'], actor).status == 'completed'
    downstream = result.model_copy(update={'job': source.job})
    assert run(repo, downstream)
    citation = service.ask(principal, project.id, 'GET /health').citations[0]
    reindex = repo.command(principal.tenant_id, project.id, result.source.id, actor, 'reprocess', 'reindex-generated-vtt')
    assert run(repo, reindex) and len(media[1].calls) == 2
    with repo.store._connect() as connection:
        versions = connection.execute('SELECT generation,asr_job_id FROM processing_versions WHERE tenant_id=%s AND project_id=%s AND source_id=%s ORDER BY generation', scope).fetchall()
        assert [(row['generation'], row['asr_job_id']) for row in versions] == [(1, result.job.id), (2, result.job.id)]
    assert repo.get_source(principal.tenant_id, project.id, result.source.id).active_generation == 2
    assert citation.generation == 1
    ticket = service.delete_project(principal, project.id)
    cleanup_all(repo)
    assert not repo.artifacts.objects and repo.get_cleanup(principal.tenant_id, project.id, ticket, actor).status == 'completed'
    with repo.store._connect() as connection:
        for table in ['audio_inputs', 'asr_runs', 'asr_windows', 'source_artifacts', 'processing_versions', 'usage_events']:
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0


def test_transient_retry_keeps_original_but_exhaustion_retires_and_requires_reupload(ingestion, media):
    repo, _, principal, project, actor = ingestion
    result = register_audio(ingestion, media, frames=SAMPLE_RATE)
    media[1].error = SourceError('local_asr_unavailable', 'Fixture service is unavailable.', transient=True)
    for attempt in range(3):
        make_due(repo, result)
        assert not process(repo, result)
        job = repo.get_job(principal.tenant_id, project.id, result.job.id)
        assert job.attempt_count == attempt + 1
        assert job.status == ('failed' if attempt == 2 else 'retrying')
        with repo.store._connect() as connection:
            raw = connection.execute('SELECT cleanup_id FROM audio_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, result.job.id)).fetchone()
            assert (raw['cleanup_id'] is not None) == (attempt == 2)
    for command in ['retry', 'reprocess']:
        with pytest.raises(SourceError) as error: repo.command(principal.tenant_id, project.id, result.source.id, actor, command, 'retired-' + command)
        assert error.value.code == 'audio_reupload_required'
    cleanup_all(repo)
    assert not repo.artifacts.objects and len(media[1].calls) == 3


def test_adoption_rollback_orphans_cannot_delete_a_later_adopted_candidate(ingestion, media):
    repo, _, principal, project, _ = ingestion
    result = register_audio(ingestion, media, frames=SAMPLE_RATE)
    def fail_after_put(): raise RuntimeError('private payload and credential must never reach logs')
    repo.artifacts.after_put = fail_after_put
    assert not process(repo, result)
    assert len(media[1].calls) == 1 and len(repo.artifacts.objects) == 2
    repo.artifacts.after_put = None
    make_due(repo, result)
    assert process(repo, result) and len(media[1].calls) == 1  # Saved final window reused, no new inference.
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    with repo.store._connect() as connection:
        adopted = connection.execute('SELECT object_key FROM source_artifacts WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (principal.tenant_id, project.id, result.source.id)).fetchone()['object_key']
    cleanup_all(repo)
    assert list(repo.artifacts.objects) == [adopted]
    assert run(repo, result.model_copy(update={'job': source.job}))


@pytest.mark.parametrize('action', ['cancel', 'revoked', 'expired', 'source_delete', 'project_delete'])
def test_inflight_invalidation_never_adopts_and_cleanup_removes_only_owned_objects(ingestion, media, action):
    repo, service, principal, project, actor = ingestion
    result = register_audio(ingestion, media, frames=SAMPLE_RATE)
    foreign_key = 'foreign-tenant/' + str(uuid4()) + '/' + str(uuid4()) + '/keep'
    repo.artifacts.objects[foreign_key] = b'foreign object is not ours'
    def invalidate():
        if action == 'cancel': repo.command(principal.tenant_id, project.id, result.source.id, actor, 'cancel', 'cancel-inflight-audio')
        elif action == 'source_delete': repo.delete_source(principal.tenant_id, project.id, result.source.id, actor)
        elif action == 'project_delete': service.delete_project(principal, project.id)
        else:
            with repo.store._connect() as connection:
                if action == 'revoked': connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
                else: connection.execute("UPDATE audio_inputs SET expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", (principal.tenant_id, project.id, result.job.id))
    media[1].after_call = invalidate
    assert not process(repo, result)
    retire_unusable_audio(repo)
    cleanup_all(repo)
    assert repo.artifacts.objects == {foreign_key: b'foreign object is not ours'}
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM source_artifacts WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM content_segments WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0


@pytest.mark.parametrize('previous_attempts', [0, 5])
def test_idle_expiry_revocation_and_cleanup_failure_are_observable(ingestion, media, previous_attempts):
    repo, _, principal, project, actor = ingestion
    result = register_audio(ingestion, media)
    with repo.store._connect() as connection:
        connection.execute("UPDATE audio_inputs SET expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", (principal.tenant_id, project.id, result.job.id))
    assert retire_unusable_audio(repo) == 1
    assert not process(repo, result) and not media[1].calls
    assert repo.get_job(principal.tenant_id, project.id, result.job.id).failure_code == 'audio_expired'
    cleanup_id = UUID(repo.get_source(principal.tenant_id, project.id, result.source.id).metadata['audio_cleanup_id'])
    with repo.store._connect() as connection:
        connection.execute('UPDATE artifact_cleanup SET attempt_count=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
                           (previous_attempts, principal.tenant_id, project.id, cleanup_id))
    repo.artifacts.fail_delete = True
    assert cleanup_once(repo) == 0 and repo.artifacts.objects
    assert repo.get_cleanup(principal.tenant_id, project.id, cleanup_id, actor).status == ('pending' if previous_attempts == 0 else 'failed')
    assert 'tutorial_audio_originals{status="cleanup_pending"} 1\n' in repo.render_metrics()
    repo.artifacts.fail_delete = False
    with repo.store._connect() as connection:
        connection.execute("UPDATE artifact_cleanup SET status='pending',attempt_count=0,available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, cleanup_id))
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert retire_unusable_audio(repo) == 0


@pytest.mark.parametrize('boundary', ['registration', 'adoption'])
def test_membership_revocation_after_object_put_cannot_adopt_an_artifact(ingestion, media, boundary):
    repo, _, principal, project, actor = ingestion
    result = register_audio(ingestion, media, frames=SAMPLE_RATE) if boundary == 'adoption' else None
    def revoke():
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    repo.artifacts.after_put = revoke
    if boundary == 'registration':
        with pytest.raises(ProjectNotFoundError): register_audio(ingestion, media)
    else:
        assert not process(repo, result)
        assert retire_unusable_audio(repo) == 1
    repo.artifacts.after_put = None
    cleanup_all(repo)
    assert not repo.artifacts.objects
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM source_artifacts WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0


def test_registration_isolation_archive_and_rollback_orphan_cleanup(ingestion, media):
    repo, service, principal, project, actor = ingestion
    other = service.create_project(principal, ProjectCreate(title='Other'))
    foreign = AuthenticatedPrincipal(provider='test', subject='foreign', tenant_id='foreign')
    foreign_actor = repo.store.bootstrap_principal(foreign)
    for tenant, project_id, user in [(foreign.tenant_id, project.id, foreign_actor), (principal.tenant_id, other.id, foreign_actor)]:
        with pytest.raises(ProjectNotFoundError):
            media[0].register(tenant, project_id, user, filename='owned.wav', content=wav_bytes(), rights=AuthorizationMode.OWNER_UPLOAD, language='en', idempotency_key='foreign-audio-key')
    assert not repo.artifacts.objects
    service.archive_project(principal, project.id)
    with pytest.raises(SourceError) as error: register_audio(ingestion, media)
    assert error.value.code == 'project_archived'
    service.restore_project(principal, project.id)
    repo.artifacts.after_put = lambda: (_ for _ in ()).throw(RuntimeError('fixture rollback'))
    with pytest.raises(RuntimeError): register_audio(ingestion, media)
    assert repo.artifacts.objects
    repo.artifacts.after_put = None
    cleanup_all(repo)
    assert not repo.artifacts.objects


@pytest.mark.parametrize('foreign_scope', ['project', 'tenant'])
def test_original_cannot_reference_a_cleanup_ticket_from_another_scope(ingestion, media, foreign_scope):
    repo, service, principal, project, actor = ingestion
    result = register_audio(ingestion, media)
    owner = principal if foreign_scope == 'project' else AuthenticatedPrincipal(provider='test', subject='foreign-cleanup', tenant_id='foreign-cleanup')
    other = service.create_project(owner, ProjectCreate(title='Foreign cleanup'))
    other_actor = repo.store.bootstrap_principal(owner)
    cleanup = uuid4()
    with repo.store._connect() as connection:
        connection.execute('INSERT INTO artifact_cleanup(id,tenant_id,project_id,actor_user_id,object_prefix) VALUES(%s,%s,%s,%s,%s)',
                           (cleanup, owner.tenant_id, other.id, other_actor, f'{owner.tenant_id}/{other.id}/'))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute('UPDATE audio_inputs SET cleanup_id=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                               (cleanup, principal.tenant_id, project.id, result.job.id))


def test_generated_vtt_respects_the_configured_downstream_upload_limit(ingestion, media):
    repo, _, principal, project, _ = ingestion
    result = register_audio(ingestion, media, frames=SAMPLE_RATE)
    repo.settings = replace(repo.settings, upload_limit_bytes=1)
    assert not process(repo, result)
    assert repo.get_job(principal.tenant_id, project.id, result.job.id).failure_code == 'derived_transcript_limit'
    cleanup_all(repo)
    assert not repo.artifacts.objects
