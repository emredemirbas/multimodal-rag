"""Private component fixtures only: no product WAV upload/retention is enabled."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.asr.checkpoints import AsrCheckpoints
from app.asr.wav import SAMPLE_RATE, SLICE_FRAMES
from app.jobs.dispatch import cleanup_once
from app.jobs.processing import process_transcript
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.transcripts import parse_transcript
from test_asr_transcript import speech
from test_ingestion_integration import ingestion, register, run
from test_postgres_integration import isolated_postgres_url
from test_wav import wav_bytes

pytestmark = pytest.mark.integration


def seeded_audio(ingestion, frames=SLICE_FRAMES + SAMPLE_RATE):
    repo, _, principal, project, actor = ingestion
    content, source = wav_bytes(frames), uuid4()
    with repo.store._connect() as connection:
        repo._project(connection, principal.tenant_id, project.id, actor)
        connection.execute(
            '''INSERT INTO sources (tenant_id,project_id,id,filename,kind,authorization_mode,status,
               processing_version,idempotency_key,content_sha256) VALUES (%s,%s,%s,'owned.wav','audio',
               'owner_upload','created','asr-fixture-v1',%s,%s)''',
            (principal.tenant_id, project.id, source, uuid4().hex, hashlib.sha256(content).hexdigest()),
        )
        job = repo._new_job(connection, principal.tenant_id, project.id, source, actor, 1, 'asr')
    # WAV exists only in this test's memory. This is deliberately not registration
    # or an implicit original-retention policy; no object-store call is made.
    return source, job.id, content


def claim_audio(ingestion, source, job):
    repo, _, principal, project, _ = ingestion
    return repo.claim_job(principal.tenant_id, project.id, source, job, 1, job_types=('asr',))


def scope(claim):
    return claim['tenant_id'], claim['project_id'], claim['id']


def test_private_ordered_windows_resume_after_real_lease_recovery_without_publishing(ingestion, caplog):
    repo, service, principal, project, _ = ingestion
    old = register(ingestion)
    assert run(repo, old)
    citation = service.ask(principal, project.id, 'GET /health').citations[0]
    source, job, content = seeded_audio(ingestion)
    assert not process_transcript(repo, principal.tenant_id, project.id, source, job, 1)
    assert repo.get_job(principal.tenant_id, project.id, job).attempt_count == 0
    claim = claim_audio(ingestion, source, job)
    checkpoints = AsrCheckpoints(repo)
    assert checkpoints.begin(claim, 'owned.wav', content, 'en').next_window == 0
    with pytest.raises(SourceError) as error:
        checkpoints.assemble(claim)
    assert error.value.code == 'asr_checkpoint_incomplete'
    assert not checkpoints.save(claim, 1, speech())
    caplog.set_level(logging.INFO, logger='tutorial_workspace.jobs')
    assert checkpoints.save(claim, 0, speech(SLICE_FRAMES, text='private checkpoint speech'))
    assert not checkpoints.save(claim, 0, speech(SLICE_FRAMES, text='must not overwrite'))
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(claim))
    assert checkpoints.begin(claim, 'owned.wav', content, 'en') is None
    assert not checkpoints.save(claim, 1, speech()) and checkpoints.assemble(claim) is None
    assert repo.recover_leases() == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(claim))
    resumed = claim_audio(ingestion, source, job)
    cursor = checkpoints.begin(resumed, 'owned.wav', content, 'en')
    assert (cursor.next_window, cursor.total_windows, cursor.completed_frames) == (1, 2, SLICE_FRAMES)
    assert not checkpoints.save(claim, 1, speech())
    assert checkpoints.save(resumed, 1, speech())
    derived = checkpoints.assemble(resumed)
    assert derived == checkpoints.assemble(resumed)
    assert [cue.start_ms for cue in parse_transcript(derived.content.decode())] == [0, 30_000]
    assert derived.model_duration_ms == 34 and derived.segments == 2
    assert repo.get_source(principal.tenant_id, project.id, source).active_generation is None
    assert repo.get_job(principal.tenant_id, project.id, job).status == 'running'
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (principal.tenant_id, project.id, source)).fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['n'] == 0
    assert service.ask(principal, project.id, 'GET /health').citations[0].segment_id == citation.segment_id
    assert 'private checkpoint speech' not in caplog.text and 'must not overwrite' not in caplog.text
    metrics = repo.render_metrics()
    assert 'tutorial_asr_saved_windows 2\n' in metrics and 'tutorial_asr_staged_input_frames 496000\n' in metrics
    assert 'private checkpoint speech' not in metrics


def test_concurrent_save_accepts_one_result_and_does_not_duplicate_usage(ingestion):
    repo, _, _, _, _ = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    checkpoints.begin(claim, 'owned.wav', content, 'en')
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved = list(pool.map(lambda _: checkpoints.save(claim, 0, speech()), range(2)))
    assert sorted(saved) == [False, True]
    assert checkpoints.assemble(claim).model_duration_ms == 17
    with repo.store._connect() as connection:
        row = connection.execute('SELECT next_window,completed_frames,model_duration_ms FROM asr_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()
    assert tuple(row.values()) == (1, SAMPLE_RATE, 17)


def test_changed_input_profile_language_and_invalid_results_never_advance(ingestion):
    repo, _, _, _, _ = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    checkpoints.begin(claim, 'owned.wav', content, 'en')
    for changed, language in [(content[:-1] + b'\x01', 'en'), (content, 'tr')]:
        with pytest.raises(SourceError) as error:
            checkpoints.begin(claim, 'owned.wav', changed, language)
        assert error.value.code == 'asr_input_changed'
    for value in [speech(100), speech(language='tr'), {**speech().model_dump(mode='json'), 'engine': 'changed'}]:
        with pytest.raises(SourceError):
            checkpoints.save(claim, 0, value)
    for ordinal in [True, -1, 20, 1.5]:
        with pytest.raises(SourceError):
            checkpoints.save(claim, ordinal, speech())
    for language in [None, [], 'remote']:
        with pytest.raises(SourceError):
            checkpoints.begin(claim, 'owned.wav', content, language)
    assert checkpoints.begin(claim, 'owned.wav', content, 'en').next_window == 0
    with repo.store._connect() as connection:
        connection.execute("UPDATE asr_runs SET profile='changed' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", scope(claim))
    for operation in [lambda: checkpoints.begin(claim, 'owned.wav', content, 'en'), lambda: checkpoints.save(claim, 0, speech()), lambda: checkpoints.assemble(claim)]:
        with pytest.raises(SourceError) as error:
            operation()
        assert error.value.code == 'asr_profile_changed'


@pytest.mark.parametrize('fence', ['tenant', 'project', 'source', 'generation', 'token', 'cancel', 'membership', 'delete_source', 'delete_project'])
def test_every_operation_checks_scope_live_actor_generation_lease_and_deletion(ingestion, fence):
    repo, service, principal, project, actor = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    checkpoints.begin(claim, 'owned.wav', content, 'en')
    assert checkpoints.save(claim, 0, speech())
    changed = dict(claim)
    if fence == 'tenant':
        outsider = AuthenticatedPrincipal(provider='test', subject='other', tenant_id='other')
        service.create_project(outsider, ProjectCreate(title='Other'))
        changed['tenant_id'] = outsider.tenant_id
        changed['actor_user_id'] = repo.store.bootstrap_principal(outsider)
    elif fence == 'project':
        changed['project_id'] = service.create_project(principal, ProjectCreate(title='Other')).id
    elif fence == 'source': changed['source_id'] = seeded_audio(ingestion, SAMPLE_RATE)[0]
    elif fence == 'generation': changed['generation'] += 1
    elif fence == 'token': changed['lease_token'] = uuid4()
    elif fence == 'cancel': repo.command(principal.tenant_id, project.id, source, actor, 'cancel', 'cancel-audio-fixture')
    elif fence == 'membership':
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    elif fence == 'delete_source': repo.delete_source(principal.tenant_id, project.id, source, actor)
    elif fence == 'delete_project': service.delete_project(principal, project.id)
    assert checkpoints.begin(changed, 'owned.wav', content, 'en') is None
    assert not checkpoints.save(changed, 0, speech()) and checkpoints.assemble(changed) is None
    if fence.startswith('delete_'):
        with repo.store._connect() as connection:
            for table in ['asr_windows', 'asr_runs']:
                assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['n'] == 0
        assert cleanup_once(repo) == 1


@pytest.mark.parametrize('corrupt', ['missing_window', 'result', 'digest', 'frames', 'usage', 'assembly', 'source_digest'])
def test_incomplete_or_corrupted_staging_is_not_returned_as_an_artifact(ingestion, corrupt):
    repo, _, _, _, _ = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    checkpoints.begin(claim, 'owned.wav', content, 'en')
    assert checkpoints.save(claim, 0, speech())
    with repo.store._connect() as connection:
        if corrupt == 'missing_window': connection.execute('DELETE FROM asr_windows WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim))
        elif corrupt == 'result': connection.execute('UPDATE asr_windows SET result=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (Jsonb(speech(text='changed text').model_dump(mode='json')), *scope(claim)))
        elif corrupt == 'digest': connection.execute("UPDATE asr_windows SET result_sha256=repeat('0',64) WHERE tenant_id=%s AND project_id=%s AND job_id=%s", scope(claim))
        elif corrupt == 'frames': connection.execute('UPDATE asr_windows SET input_frames=1 WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim))
        elif corrupt == 'usage': connection.execute('UPDATE asr_runs SET model_duration_ms=1000 WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim))
        elif corrupt == 'assembly': connection.execute("UPDATE asr_runs SET assembly_version='changed' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", scope(claim))
        else: connection.execute("UPDATE sources SET content_sha256=repeat('0',64) WHERE tenant_id=%s AND project_id=%s AND id=%s", (claim['tenant_id'], claim['project_id'], claim['source_id']))
    with pytest.raises(SourceError): checkpoints.assemble(claim)


def test_scoped_foreign_keys_cannot_attach_a_window_to_a_different_source(ingestion):
    repo, _, _, _, _ = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    checkpoints.begin(claim, 'owned.wav', content, 'en')
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute('''INSERT INTO asr_windows (tenant_id,project_id,job_id,source_id,generation,ordinal,input_frames,result,result_sha256)
                VALUES (%s,%s,%s,%s,1,0,16000,%s,%s)''', (*scope(claim), uuid4(), Jsonb(speech().model_dump(mode='json')), '0' * 64))


def test_migration_preserves_published_evidence_and_does_not_create_public_uploads(ingestion):
    repo, service, principal, project, _ = ingestion
    result = register(ingestion)
    assert run(repo, result)
    citation = service.ask(principal, project.id, 'GET /health').citations[0]
    repo.store.run_migrations()
    assert service.ask(principal, project.id, 'GET /health').citations[0].segment_id == citation.segment_id
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM asr_runs').fetchone()['n'] == 0
    ordinary = register(ingestion, key='ordinary-new-input')
    claim = repo.claim_job(principal.tenant_id, project.id, ordinary.source.id, ordinary.job.id, 1)
    with pytest.raises(SourceError) as error:
        AsrCheckpoints(repo).begin(claim, 'owned.wav', wav_bytes(), 'en')
    assert error.value.code == 'asr_input_changed'


def test_uninitialized_and_all_silent_runs_never_produce_a_transcript(ingestion):
    repo, _, _, _, _ = ingestion
    source, job, content = seeded_audio(ingestion, SAMPLE_RATE)
    claim, checkpoints = claim_audio(ingestion, source, job), AsrCheckpoints(repo)
    for operation in [lambda: checkpoints.save(claim, 0, speech()), lambda: checkpoints.assemble(claim)]:
        with pytest.raises(SourceError) as error: operation()
        assert error.value.code == 'asr_checkpoint_missing'
    checkpoints.begin(claim, 'owned.wav', content, 'auto')
    silent = speech(language='auto', silent=True)
    silent.language_probability = -0.0  # JSONB canonicalizes this legal probability.
    assert checkpoints.save(claim, 0, silent)
    with pytest.raises(SourceError) as error: checkpoints.assemble(claim)
    assert error.value.code == 'no_speech_detected'
