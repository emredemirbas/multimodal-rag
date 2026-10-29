"""Private synthetic DB snapshots; no product video registration/native inference."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.jobs.dispatch import cleanup_once
from app.jobs.processing import process_transcript
from app.config import Settings
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest, AuthorizationMode
from app.postgres import PostgresStore
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.sources.contracts import SourceError
from app.sources.repository import SourceRepository
from app.vision.checkpoints import VisualCheckpoints, CHECKPOINT_VERSION
from app.vision.contracts import WireResult
from app.vision.local import VisualResult
from app.vision.media import FrameEvidence, VideoInfo, encode_png
from test_ingestion_integration import MemoryArtifacts, ingestion, register, run
from test_postgres_integration import isolated_postgres_url
from test_visual_service import content, identity, result
from test_visual_selection import change_result

pytestmark = pytest.mark.integration


def seed(ingestion):
    repo, _, principal, project, actor = ingestion
    source, data = uuid4(), content()
    with repo.store._connect() as connection:
        repo._project(connection, principal.tenant_id, project.id, actor)
        connection.execute(
            '''INSERT INTO sources (tenant_id,project_id,id,filename,kind,authorization_mode,status,
               processing_version,idempotency_key,content_sha256) VALUES (%s,%s,%s,'owned.mp4','video',
               'owner_upload','created','visual-private-fixture-v1',%s,%s)''',
            (principal.tenant_id, project.id, source, uuid4().hex, hashlib.sha256(data).hexdigest()),
        )
        job = repo._new_job(connection, principal.tenant_id, project.id, source, actor, 1, 'visual')
    return source, job.id, data


def claim_for(ingestion, source, job):
    repo, _, principal, project, _ = ingestion
    return repo.claim_job(principal.tenant_id, project.id, source, job, 1, job_types=('visual',))


def scope(claim):
    return claim['tenant_id'], claim['project_id'], claim['id']


def saved(ingestion, snapshot=None):
    source, job, data = seed(ingestion)
    claim = claim_for(ingestion, source, job)
    checkpoints = VisualCheckpoints(ingestion[0])
    snapshot = snapshot or WireResult.from_result(result())
    assert not checkpoints.begin(claim, data, snapshot.identity).result_saved
    assert checkpoints.save(claim, snapshot)
    return claim, checkpoints, data


def test_private_snapshot_survives_real_lease_recovery_without_publishing_or_reinference(ingestion, caplog):
    repo, service, principal, project, _ = ingestion
    previous = register(ingestion)
    assert run(repo, previous)
    citation = service.ask(principal, project.id, 'GET /health').citations[0]
    caplog.set_level(logging.INFO, logger='tutorial_workspace.jobs')
    claim, checkpoints, data = saved(ingestion)
    assert not process_transcript(repo, principal.tenant_id, project.id, claim['source_id'], claim['id'], 1)
    assert checkpoints.load(claim) == result()
    assert not checkpoints.save(claim, result())
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(claim))
    assert checkpoints.begin(claim, data, identity()) is None
    assert not checkpoints.save(claim, result()) and checkpoints.load(claim) is None
    assert repo.recover_leases() == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(claim))
    resumed = claim_for(ingestion, claim['source_id'], claim['id'])
    cursor = checkpoints.begin(resumed, data, identity())
    assert cursor.result_saved and cursor.saved_frames == 2
    assert checkpoints.load(resumed) == result()
    assert not checkpoints.save(claim, result())
    current = repo.get_source(principal.tenant_id, project.id, claim['source_id'])
    assert current.active_generation is None and current.frame_count == current.segment_count == 0
    assert current.job.status == 'running'
    assert service.ask(principal, project.id, 'GET /health').citations[0].segment_id == citation.segment_id
    with repo.store._connect() as connection:
        for table in ['content_segments', 'processing_versions', 'usage_events']:
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                      (claim['tenant_id'], claim['project_id'], claim['source_id'])).fetchone()['n'] == 0
    assert 'PRIVATE_OCR' not in caplog.text and 'user_id' not in caplog.text and 'owned.mp4' not in caplog.text
    metrics = repo.render_metrics()
    assert 'tutorial_visual_checkpoint_frames 2\n' in metrics and 'tutorial_visual_runs{status="saved"} 1\n' in metrics
    assert 'PRIVATE_OCR' not in metrics and str(claim['source_id']) not in metrics


def test_concurrent_begin_and_save_accept_exactly_one_snapshot_and_never_overwrite(ingestion):
    source, job, data = seed(ingestion)
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(ingestion[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        cursors = list(pool.map(lambda _: checkpoints.begin(claim, data, identity()), range(2)))
    assert all(not cursor.result_saved for cursor in cursors)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: checkpoints.save(claim, result()), range(2)))
    assert sorted(values) == [False, True]
    changed = WireResult.from_result(result()).model_dump()
    changed['frames'][0]['text'] = 'must never replace accepted OCR'
    assert not checkpoints.save(claim, changed)
    assert checkpoints.load(claim) == result()
    cursor = checkpoints.begin(claim, data, identity())
    assert cursor.ocr_characters == sum(len(f.text) for f in result().frames)
    assert cursor.image_bytes == sum(len(f.image) for f in result().frames)
    job = ingestion[0].get_job(claim['tenant_id'], claim['project_id'], claim['id'])
    assert job.status == 'running' and job.stage == 'visual_checkpointed' and job.progress_percent == 60


def test_ordinary_and_audio_workers_do_not_claim_pending_visual_jobs(ingestion):
    repo, _, principal, project, _ = ingestion
    source, job, _ = seed(ingestion)
    assert repo.claim_job(principal.tenant_id, project.id, source, job, 1) is None
    assert repo.claim_job(principal.tenant_id, project.id, source, job, 1, job_types=('asr',)) is None
    assert not process_transcript(repo, principal.tenant_id, project.id, source, job, 1)
    assert repo.get_job(principal.tenant_id, project.id, job).attempt_count == 0


def test_max_frame_count_and_unicode_character_byte_bounds_roundtrip(ingestion):
    source, job, data = seed(ingestion)
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(ingestion[0])
    checkpoints.begin(claim, data, identity())
    text = '\U0001f600' * 16000  # 16,000 code points / 64,000 UTF-8 bytes per frame.
    frames = tuple(FrameEvidence(sample_target_ms=i * 30000, timestamp_ms=i * 30000,
        width=16, height=16, image=encode_png(16, 16, bytes([i]) * 256), text=text) for i in range(20))
    snapshot = VisualResult(hashlib.sha256(data).hexdigest(), VideoInfo(duration_ms=600000, width=1920,
        height=1080, fps_numerator=25, fps_denominator=1), identity().model_dump(), 20, frames)
    assert checkpoints.save(claim, snapshot)
    cursor = checkpoints.begin(claim, data, identity())
    assert cursor.saved_frames == 20 and cursor.ocr_characters == 320000
    assert checkpoints.load(claim) == snapshot


@pytest.mark.parametrize('fence', ['tenant', 'project', 'source', 'generation', 'token', 'actor', 'cancel',
    'membership', 'delete_source', 'delete_project', 'lease', 'expiry', 'cancellation_flag'])
@pytest.mark.parametrize('selection_version', [1, 2])
def test_all_operations_fence_scope_initiating_actor_generation_token_and_eligibility(ingestion, fence, selection_version):
    repo, service, principal, project, actor = ingestion
    snapshot = change_result() if selection_version == 2 else WireResult.from_result(result())
    claim, checkpoints, data = saved(ingestion, snapshot)
    changed = dict(claim)
    if fence == 'tenant':
        outsider = AuthenticatedPrincipal(provider='test', subject='other', tenant_id='other')
        service.create_project(outsider, ProjectCreate(title='Other'))
        changed['tenant_id'] = outsider.tenant_id
        changed['actor_user_id'] = repo.store.bootstrap_principal(outsider)
    elif fence == 'project': changed['project_id'] = service.create_project(principal, ProjectCreate(title='Other')).id
    elif fence == 'source': changed['source_id'] = seed(ingestion)[0]
    elif fence == 'generation': changed['generation'] += 1
    elif fence == 'token': changed['lease_token'] = uuid4()
    elif fence == 'actor':
        other = AuthenticatedPrincipal(provider='test', subject='same-tenant-other-member', tenant_id=principal.tenant_id)
        changed['actor_user_id'] = repo.store.bootstrap_principal(other)
    elif fence == 'cancel': repo.command(principal.tenant_id, project.id, claim['source_id'], actor, 'cancel', 'cancel-visual-fixture')
    elif fence == 'membership':
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    elif fence == 'delete_source': repo.delete_source(principal.tenant_id, project.id, claim['source_id'], actor)
    elif fence == 'delete_project': service.delete_project(principal, project.id)
    else:
        column = 'lease_expires_at' if fence == 'lease' else 'created_at' if fence == 'expiry' else 'cancellation_requested_at'
        expression = "now()-interval '2 hours'" if fence == 'expiry' else "now()-interval '1 second'"
        with repo.store._connect() as connection:
            connection.execute(f'UPDATE processing_jobs SET {column}={expression} WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(claim))
    assert checkpoints.begin(changed, data, snapshot.identity) is None
    assert not checkpoints.save(changed, snapshot) and checkpoints.load(changed) is None
    if fence.startswith('delete_'):
        with repo.store._connect() as connection:
            for table in ['visual_runs', 'visual_checkpoint_frames']:
                assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['n'] == 0
        assert cleanup_once(repo) == 1


def test_changed_input_language_profile_rights_and_job_kind_never_advance(ingestion):
    repo = ingestion[0]
    source, job, data = seed(ingestion)
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(repo)
    checkpoints.begin(claim, data, identity())
    for changed_data, pin in [(data[:-1] + b'x', identity()), (data, identity('tr')), (data, identity(version='5.1.10'))]:
        with pytest.raises(SourceError):
            checkpoints.begin(claim, changed_data, pin)
    for value in [result(b'wrong input'), result(language='tr')]:
        with pytest.raises(SourceError, match='pinned'):
            checkpoints.save(claim, value)
    for field, value in [('kind', 'transcript'), ('content_sha256', 'f' * 64), ('authorization_mode', 'authorized_upload')]:
        with repo.store._connect() as connection:
            original = connection.execute(f'SELECT {field} FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s',
                (claim['tenant_id'], claim['project_id'], source)).fetchone()[field]
            connection.execute(f'UPDATE sources SET {field}=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
                (value, claim['tenant_id'], claim['project_id'], source))
        for operation in [lambda: checkpoints.begin(claim, data, identity()), lambda: checkpoints.save(claim, result()), lambda: checkpoints.load(claim)]:
            with pytest.raises(SourceError): operation()
        with repo.store._connect() as connection:
            connection.execute(f'UPDATE sources SET {field}=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
                (original, claim['tenant_id'], claim['project_id'], source))
    assert not checkpoints.begin(claim, data, identity()).result_saved
    ordinary = register(ingestion)
    ordinary_claim = repo.claim_job(ingestion[2].tenant_id, ingestion[3].id, ordinary.source.id, ordinary.job.id, 1)
    with pytest.raises(SourceError): checkpoints.begin(ordinary_claim, data, identity())


@pytest.mark.parametrize('corrupt', ['missing_frame', 'text', 'text_digest', 'png', 'png_digest', 'timestamp',
    'video', 'candidates', 'result_digest', 'characters', 'bytes', 'profile', 'identity', 'version', 'expiry', 'actor', 'ordinal'])
def test_corrupted_private_snapshot_is_never_returned(ingestion, corrupt):
    repo = ingestion[0]
    claim, checkpoints, _ = saved(ingestion)
    with repo.store._connect() as connection:
        parameters = scope(claim)
        frame_where = ' WHERE tenant_id=%s AND project_id=%s AND job_id=%s AND ordinal=0'
        run_where = ' WHERE tenant_id=%s AND project_id=%s AND job_id=%s'
        if corrupt == 'missing_frame': connection.execute('DELETE FROM visual_checkpoint_frames' + frame_where, parameters)
        elif corrupt == 'text': connection.execute("UPDATE visual_checkpoint_frames SET ocr_text='altered OCR'" + frame_where, parameters)
        elif corrupt == 'text_digest': connection.execute("UPDATE visual_checkpoint_frames SET text_sha256=repeat('0',64)" + frame_where, parameters)
        elif corrupt == 'png': connection.execute('UPDATE visual_checkpoint_frames SET image=%s' + frame_where, (b'PRIVATE_NOT_PNG', *parameters))
        elif corrupt == 'png_digest': connection.execute("UPDATE visual_checkpoint_frames SET image_sha256=repeat('0',64)" + frame_where, parameters)
        elif corrupt == 'timestamp': connection.execute('UPDATE visual_checkpoint_frames SET timestamp_ms=1' + frame_where, parameters)
        elif corrupt == 'ordinal': connection.execute('UPDATE visual_checkpoint_frames SET ordinal=19' + frame_where, parameters)
        elif corrupt == 'video': connection.execute('UPDATE visual_runs SET video_metadata=%s' + run_where, (Jsonb({'private': 'bad metadata'}), *parameters))
        elif corrupt == 'candidates': connection.execute('UPDATE visual_runs SET candidates=3' + run_where, parameters)
        elif corrupt == 'result_digest': connection.execute("UPDATE visual_runs SET result_sha256=repeat('0',64)" + run_where, parameters)
        elif corrupt in {'characters', 'bytes'}:
            column = 'ocr_characters' if corrupt == 'characters' else 'image_bytes'
            connection.execute(f'UPDATE visual_runs SET {column}={column}+1' + run_where, parameters)
        elif corrupt == 'profile': connection.execute('UPDATE visual_runs SET profile=%s' + run_where, (identity('tr').profile, *parameters))
        elif corrupt == 'identity': connection.execute('UPDATE visual_runs SET identity=%s' + run_where, (Jsonb(identity('tr').model_dump()), *parameters))
        elif corrupt == 'version': connection.execute("UPDATE visual_runs SET checkpoint_version='different'" + run_where, parameters)
        elif corrupt == 'expiry': connection.execute("UPDATE visual_runs SET processing_expires_at=processing_expires_at-interval '1 second'" + run_where, parameters)
        elif corrupt == 'actor': connection.execute('UPDATE visual_runs SET actor_user_id=%s' + run_where, (uuid4(), *parameters))
    with pytest.raises(SourceError): checkpoints.load(claim)


def test_missing_incomplete_malformed_and_mutated_models_are_rejected_without_writes(ingestion):
    source, job, data = seed(ingestion)
    checkpoints, claim = VisualCheckpoints(ingestion[0]), claim_for(ingestion, source, job)
    for operation in [lambda: checkpoints.save(claim, result()), lambda: checkpoints.load(claim)]:
        with pytest.raises(SourceError) as failure: operation()
        assert failure.value.code == 'visual_checkpoint_missing'
    checkpoints.begin(claim, data, identity())
    with pytest.raises(SourceError) as failure: checkpoints.load(claim)
    assert failure.value.code == 'visual_checkpoint_incomplete'
    mutable = WireResult.from_result(result())
    mutable.frames.clear()
    for value in [mutable, {}, None, {'frames': ['bad']}]:
        with pytest.raises(SourceError) as failure: checkpoints.save(claim, value)
        assert failure.value.code == 'invalid_visual_checkpoint'
    for value in [None, {}, {**identity().model_dump(), 'profile': 'bad'}]:
        with pytest.raises(SourceError): checkpoints.begin(claim, data, value)
    assert not checkpoints.begin(claim, data, identity()).result_saved


@pytest.mark.parametrize('operation', ['begin', 'save'])
def test_eligibility_lost_before_commit_rolls_back_all_new_rows(ingestion, monkeypatch, operation):
    repo = ingestion[0]
    source, job, data = seed(ingestion)
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(repo)
    if operation == 'save': checkpoints.begin(claim, data, identity())
    original, calls = checkpoints._live, []
    def lose_after_write(connection, claim):
        calls.append(1)
        return original(connection, claim) if len(calls) == 1 else None
    monkeypatch.setattr(checkpoints, '_live', lose_after_write)
    if operation == 'begin': assert checkpoints.begin(claim, data, identity()) is None
    else: assert not checkpoints.save(claim, result())
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['n'] == 0
        run = connection.execute('SELECT saved_at FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()
        assert run is None if operation == 'begin' else run['saved_at'] is None


def test_scoped_foreign_keys_and_failed_multi_frame_write_are_atomic(ingestion):
    repo = ingestion[0]
    source, job, data = seed(ingestion)
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(repo)
    checkpoints.begin(claim, data, identity())
    _, other_job, _ = seed(ingestion)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute('''INSERT INTO visual_runs (tenant_id,project_id,job_id,source_id,generation,actor_user_id,
                authorization_mode,input_sha256,input_bytes,identity,profile,checkpoint_version,processing_expires_at)
                VALUES (%s,%s,%s,%s,1,%s,'owner_upload',%s,%s,%s,%s,%s,now()+interval '1 minute')''',
                (claim['tenant_id'], claim['project_id'], other_job, source, claim['actor_user_id'], hashlib.sha256(data).hexdigest(), len(data),
                 Jsonb(identity().model_dump()), identity().profile, CHECKPOINT_VERSION))
    with repo.store._connect() as connection:
        connection.execute("ALTER TABLE visual_checkpoint_frames ADD CONSTRAINT fixture_abort_second CHECK (ordinal != 1)")
    with pytest.raises(psycopg.errors.CheckViolation): checkpoints.save(claim, result())
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['n'] == 0
        connection.execute('ALTER TABLE visual_checkpoint_frames DROP CONSTRAINT fixture_abort_second')
    assert not checkpoints.begin(claim, data, identity()).result_saved
    assert checkpoints.save(claim, result())


def test_expiry_is_job_creation_bound_and_retry_cannot_extend_it(ingestion):
    repo = ingestion[0]
    source, job, data = seed(ingestion)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET created_at=now()-interval '30 minutes' WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (ingestion[2].tenant_id, ingestion[3].id, job))
    claim, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(repo)
    checkpoints.begin(claim, data, identity())
    with repo.store._connect() as connection:
        before = connection.execute('SELECT processing_expires_at FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['processing_expires_at']
        assert 1700 < (before - connection.execute('SELECT clock_timestamp() AS time').fetchone()['time']).total_seconds() <= 1800
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(claim))
    assert repo.recover_leases() == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(claim))
    resumed = claim_for(ingestion, source, job)
    checkpoints.begin(resumed, data, identity())
    with repo.store._connect() as connection:
        assert connection.execute('SELECT processing_expires_at FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(claim)).fetchone()['processing_expires_at'] == before
    source2, job2, data2 = seed(ingestion)
    expired = claim_for(ingestion, source2, job2)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET created_at=now()-interval '2 hours' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(expired))
    assert checkpoints.begin(expired, data2, identity()) is None
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(expired)).fetchone()['n'] == 0


def test_initiating_membership_is_locked_until_private_read_transaction_finishes(ingestion, monkeypatch):
    repo = ingestion[0]
    claim, checkpoints, _ = saved(ingestion)
    entered, release = Event(), Event()
    original, calls = checkpoints._live, []
    def hold(connection, claim):
        value = original(connection, claim)
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return value
    monkeypatch.setattr(checkpoints, '_live', hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(checkpoints.load, claim)
        try:
            assert entered.wait(3)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                with repo.store._connect() as connection:
                    connection.execute("SET LOCAL lock_timeout='100ms'")
                    connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s',
                                       (claim['tenant_id'], claim['actor_user_id']))
        finally:
            release.set()
        assert future.result(timeout=3) == result()
    with repo.store._connect() as connection:
        connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s',
                           (claim['tenant_id'], claim['actor_user_id']))
    assert checkpoints.load(claim) is None


def test_additive_migration_preserves_published_pre_checkpoint_data_and_checksums(isolated_postgres_url):
    store = PostgresStore(isolated_postgres_url)
    migrations = Path(__file__).resolve().parents[1] / 'app' / 'migrations'
    with store._connect() as connection:
        connection.execute('CREATE TABLE schema_migrations (version text PRIMARY KEY,sha256 text,applied_at timestamptz NOT NULL DEFAULT now())')
        for path in sorted(migrations.glob('*.sql')):
            if path.name >= '0013_visual_checkpoints.sql': break
            script = path.read_text()
            connection.execute(script)
            connection.execute('INSERT INTO schema_migrations (version,sha256) VALUES (%s,%s)',
                               (path.name, hashlib.sha256(script.encode()).hexdigest()))
        before = connection.execute('SELECT version,sha256 FROM schema_migrations ORDER BY version').fetchall()
    principal = AuthenticatedPrincipal(provider='test', subject='visual-migration-user', tenant_id='visual-migration')
    service = TutorialService(store, DeterministicHashEmbeddingProvider(), EvidenceExtractiveAnswerProvider())
    project = service.create_project(principal, ProjectCreate(title='Existing data'))
    ingested = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(
        filename='existing.vtt', authorization_mode=AuthorizationMode.OWNER_UPLOAD, idempotency_key='existing-fixture',
        content='WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nGET /health reports service health.\n'))
    # Seed/capture the historical schema directly: the current application's search
    # correctly requires its new view, installed only by the deployment migration.
    with store._connect() as connection:
        previous = connection.execute('SELECT * FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
            (principal.tenant_id, project.id, ingested.source.id)).fetchone()
    store.run_migrations()
    store.run_migrations()
    assert service.ask(principal, project.id, 'GET /health').citations[0].segment_id == previous['id']
    with store._connect() as connection:
        preserved = connection.execute('SELECT * FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s',
            (principal.tenant_id, project.id, ingested.source.id, previous['id'])).fetchone()
        assert {key: preserved[key] for key in previous} == previous
        after = connection.execute('SELECT version,sha256 FROM schema_migrations ORDER BY version').fetchall()
        assert after[:len(before)] == before
        assert [row['version'] for row in after[len(before):]] == ['0013_visual_checkpoints.sql', '0014_video_lifecycle.sql', '0015_retained_visual_gallery.sql', '0016_retained_ocr_index.sql', '0017_video_workflows.sql', '0018_visual_selection_manifest.sql', '0019_local_frame_descriptions.sql', '0020_curriculum_contexts.sql']
        assert connection.execute('SELECT count(*) AS n FROM video_workflows').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM visual_runs WHERE tenant_id=%s AND project_id=%s',
                                   (principal.tenant_id, project.id)).fetchone()['n'] == 0
