"""Private coordinator tests with synthetic MP4/OCR, not native quality evidence."""
from concurrent.futures import ThreadPoolExecutor
import logging
from uuid import uuid4

import pytest

from app.jobs.dispatch import cleanup_once
from app.jobs import visual_processing
from app.models import AuthorizationMode, ProjectCreate
from app.sources.contracts import SourceError
from app.sources.video import VideoRepository, retire_unusable_video
from app.store import ProjectNotFoundError
from app.vision.checkpoints import VisualCheckpoints
from app.vision.client import VisualError
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_service import content, identity, result

pytestmark = pytest.mark.integration


def register_video(ingestion, **overrides):
    repo, _, principal, project, actor = ingestion
    args = dict(filename='owned.mp4', content=content(), rights=AuthorizationMode.OWNER_UPLOAD,
                language='en', idempotency_key='private-video-fixture')
    args.update(overrides)
    return VideoRepository(repo).register(principal.tenant_id, project.id, actor, **args)


def process(repo, registration):
    return visual_processing.process_video(repo, registration.source.tenant_id, registration.source.project_id,
        registration.source.id, registration.job.id, registration.job.generation)


def claim(repo, registration):
    return repo.claim_job(registration.source.tenant_id, registration.source.project_id,
        registration.source.id, registration.job.id, 1, job_types=('visual',))


def scope(registration):
    return registration.source.tenant_id, registration.source.project_id, registration.job.id


class FixtureVisual:
    def __init__(self): self.calls = []
    def ready(self, language):
        self.calls.append('ready')
        return identity(language)
    def extract(self, data, *, expected_identity):
        self.calls.append('extract')
        assert expected_identity == identity()
        return result(data)


@pytest.fixture
def provider(monkeypatch):
    fixture = FixtureVisual()
    monkeypatch.setattr(visual_processing, 'build_visual_provider', lambda settings: fixture)
    return fixture


def test_registration_is_concurrent_idempotent_and_uses_fixed_expiry(ingestion):
    repo = ingestion[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        registrations = list(pool.map(lambda _: register_video(ingestion), range(2)))
    item = registrations[0]
    assert {r.source.id for r in registrations} == {item.source.id}
    assert {r.job.id for r in registrations} == {item.job.id}
    assert sorted(r.deduplicated for r in registrations) == [False, True]
    assert len(repo.artifacts.objects) == 1
    with pytest.raises(SourceError) as error: register_video(ingestion, language='tr')
    assert error.value.code == 'idempotency_conflict'
    with repo.store._connect() as connection:
        row = connection.execute('''SELECT v.expires_at=j.created_at+interval '1 hour' AS fixed,
            (SELECT count(*) FROM outbox_events) AS outbox FROM video_inputs v JOIN processing_jobs j ON j.id=v.job_id
            WHERE v.tenant_id=%s AND v.project_id=%s AND v.job_id=%s''', scope(item)).fetchone()
        assert row['fixed'] and row['outbox'] == 1


@pytest.mark.parametrize('change,code', [({'content': b'not mp4'}, 'invalid_video_input'),
    ({'filename': 'bad.wav'}, 'invalid_video_input'), ({'filename': 'bad\n.mp4'}, 'invalid_video_input'),
    ({'idempotency_key': 'x'}, 'invalid_video_input'), ({'rights': None}, 'rights_required'),
    ({'language': 'auto'}, 'invalid_visual_language')])
def test_invalid_registration_never_puts_objects(ingestion, change, code):
    with pytest.raises(SourceError) as error: register_video(ingestion, **change)
    assert error.value.code == code and not ingestion[0].artifacts.objects


@pytest.mark.parametrize('failure', ['revoked', 'put_interrupted'])
def test_post_put_auth_failure_is_not_adopted_and_orphan_is_cleaned(ingestion, failure):
    repo, _, principal, project, actor = ingestion
    def after_put():
        if failure == 'put_interrupted': raise RuntimeError('private-storage-detail')
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    repo.artifacts.after_put = after_put
    with pytest.raises((ProjectNotFoundError, RuntimeError)): register_video(ingestion)
    assert len(repo.artifacts.objects) == 1
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM video_inputs').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM sources').fetchone()['n'] == 0
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects


def test_prepared_is_private_not_searchable_and_usage_and_cleanup_are_once(ingestion, provider, caplog):
    repo, service, principal, project, actor = ingestion
    caplog.set_level(logging.INFO, logger='tutorial_workspace.jobs')
    item = register_video(ingestion)
    assert process(repo, item) and not process(repo, item)
    current = repo.get_source(principal.tenant_id, project.id, item.source.id)
    assert current.status == 'metadata_ready' and current.job.stage == 'visual_prepared'
    assert current.active_generation is None and current.frame_count == current.segment_count == 0
    assert service.ask(principal, project.id, 'GET /health').abstained
    assert provider.calls == ['ready', 'extract']
    with repo.store._connect() as connection:
        usage = connection.execute('SELECT * FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchall()
        assert len(usage) == 1 and usage[0]['selected_frame_count'] == 2
        assert usage[0]['input_video_bytes'] == len(content()) and usage[0]['segment_count'] == 0
        assert connection.execute('SELECT count(*) AS n FROM content_segments').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames').fetchone()['n'] == 2
    metrics = repo.render_metrics()
    assert 'tutorial_video_originals{status="cleanup_pending"} 1\n' in metrics
    assert 'tutorial_visual_prepared_runs 1\n' in metrics
    assert 'PRIVATE_OCR' not in metrics + caplog.text and 'owned.mp4' not in caplog.text
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert 'tutorial_video_originals{status="deleted"} 1\n' in repo.render_metrics()
    assert register_video(ingestion).deduplicated and not repo.artifacts.objects
    with pytest.raises(SourceError) as error:
        repo.command(principal.tenant_id, project.id, item.source.id, actor, 'reprocess', 'video-reprocess-fixture')
    assert error.value.code == 'video_reupload_required'


def test_saved_checkpoint_recovery_skips_provider_and_original_get(ingestion, monkeypatch):
    repo = ingestion[0]
    item = register_video(ingestion)
    first = claim(repo, item)
    assert 239 < (first['lease_expires_at'] - first['started_at']).total_seconds() <= 240
    checkpoints = VisualCheckpoints(repo)
    checkpoints.begin(first, content(), identity())
    assert checkpoints.save(first, result())
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(item))
    assert repo.recover_leases() == 1
    make_due(repo, item)
    repo.artifacts.fail_get = True
    def forbidden(settings): raise AssertionError('Must not create provider for complete snapshot')
    monkeypatch.setattr(visual_processing, 'build_visual_provider', forbidden)
    assert process(repo, item)
    assert not VideoRepository(repo).prepare(first)
    assert repo.get_job(*scope(item)).attempt_count == 2


@pytest.mark.parametrize('failure', ['cancel', 'expired', 'revoked', 'permanent', 'exhausted'])
def test_terminal_paths_retire_original_without_any_publication(ingestion, monkeypatch, failure):
    repo, _, principal, project, actor = ingestion
    item = register_video(ingestion)
    if failure == 'cancel': repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'cancel-video-fixture')
    elif failure in {'expired', 'revoked'}:
        with repo.store._connect() as connection:
            if failure == 'expired': connection.execute("UPDATE video_inputs SET expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", scope(item))
            else: connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
        assert retire_unusable_video(repo) == 1 and retire_unusable_video(repo) == 0
    else:
        class Failing:
            def ready(self, language): raise VisualError('visual_unavailable', transient=failure == 'exhausted')
        monkeypatch.setattr(visual_processing, 'build_visual_provider', lambda settings: Failing())
        for _ in range(item.job.max_attempts if failure == 'exhausted' else 1):
            assert not process(repo, item)
            make_due(repo, item)
    with repo.store._connect() as connection:
        row = connection.execute('SELECT cleanup_id FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()
        assert row['cleanup_id'] is not None
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 0
    repo.artifacts.fail_delete = True
    assert cleanup_once(repo) == 0
    with repo.store._connect() as connection:
        assert connection.execute('SELECT deleted_at FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['deleted_at'] is None
        connection.execute('UPDATE artifact_cleanup SET available_at=now() WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id))
    repo.artifacts.fail_delete = False
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects


@pytest.mark.parametrize('field,value', [('object_key', 'foreign/project/raw.mp4'), ('content_sha256', 'f'*64),
    ('requested_language', 'tr'), ('byte_count', 999)])
def test_cached_prepare_revalidates_original_record_without_foreign_fetch(ingestion, field, value):
    repo = ingestion[0]
    item = register_video(ingestion)
    active = claim(repo, item)
    checkpoints = VisualCheckpoints(repo)
    checkpoints.begin(active, content(), identity())
    checkpoints.save(active, result())
    with repo.store._connect() as connection:
        connection.execute(f'UPDATE video_inputs SET {field}=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (value, *scope(item)))
    repo.artifacts.fail_get = True
    with pytest.raises(SourceError) as error: VideoRepository(repo).prepare(active)
    assert error.value.code == 'artifact_integrity'
    assert repo.get_job(*scope(item)).status == 'running'


@pytest.mark.parametrize('operation', ['source', 'project'])
def test_complete_deletion_removes_private_bytes_and_raw(ingestion, operation):
    repo, service, principal, project, actor = ingestion
    item = register_video(ingestion)
    active = claim(repo, item)
    checkpoints = VisualCheckpoints(repo)
    checkpoints.begin(active, content(), identity())
    checkpoints.save(active, result())
    if operation == 'source': repo.delete_source(principal.tenant_id, project.id, item.source.id, actor)
    else: service.delete_project(principal, project.id)
    assert not VideoRepository(repo).prepare(active)
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    with repo.store._connect() as connection:
        for table in ['video_inputs', 'visual_runs', 'visual_checkpoint_frames']:
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0


def test_registration_rejects_foreign_scope_and_archived_project(ingestion):
    repo, service, principal, project, actor = ingestion
    args = dict(filename='owned.mp4', content=content(), rights=AuthorizationMode.OWNER_UPLOAD, language='en', idempotency_key='scoped-video-fixture')
    for tenant, project_id, user in [('foreign', project.id, actor), (principal.tenant_id, uuid4(), actor), (principal.tenant_id, project.id, uuid4())]:
        with pytest.raises(ProjectNotFoundError): VideoRepository(repo).register(tenant, project_id, user, **args)
    with repo.store._connect() as connection:
        connection.execute("UPDATE projects SET status='archived',archived_at=now() WHERE tenant_id=%s AND id=%s", (principal.tenant_id, project.id))
    with pytest.raises(SourceError): register_video(ingestion)
    assert not repo.artifacts.objects


def test_transient_service_failure_keeps_original_then_succeeds_once(ingestion, provider, monkeypatch):
    repo = ingestion[0]
    item = register_video(ingestion)
    def busy(language): raise VisualError('visual_busy', transient=True)
    monkeypatch.setattr(provider, 'ready', busy)
    assert not process(repo, item)
    assert repo.get_job(*scope(item)).status == 'retrying' and len(repo.artifacts.objects) == 1
    with repo.store._connect() as connection:
        assert connection.execute('SELECT cleanup_id FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['cleanup_id'] is None
    monkeypatch.setattr(provider, 'ready', lambda language: identity(language))
    make_due(repo, item)
    assert process(repo, item) and provider.calls == ['extract']
    with repo.store._connect() as connection:
        usage = connection.execute('SELECT * FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()
        assert usage['billed_usd'] == 0 and usage['input_tokens'] is None
        assert usage['duration_ms'] >= 0 and usage['embedding_space'] is None


@pytest.mark.parametrize('action', ['cancel', 'revoke', 'delete_source', 'delete_project'])
def test_inflight_invalidation_never_saves_or_prepares(ingestion, provider, monkeypatch, action):
    repo, service, principal, project, actor = ingestion
    item = register_video(ingestion)
    def invalidate(data, *, expected_identity):
        if action == 'cancel': repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'inflight-video-cancel')
        elif action == 'revoke':
            with repo.store._connect() as connection:
                connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
        elif action == 'delete_source': repo.delete_source(principal.tenant_id, project.id, item.source.id, actor)
        else: service.delete_project(principal, project.id)
        return result(data)
    monkeypatch.setattr(provider, 'extract', invalidate)
    assert not process(repo, item)
    if action == 'revoke': assert retire_unusable_video(repo) == 1
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames').fetchone()['n'] == 0
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects


def test_incomplete_pinned_result_cannot_adopt_changed_provider_profile(ingestion, monkeypatch):
    repo = ingestion[0]
    item = register_video(ingestion)
    active = claim(repo, item)
    VisualCheckpoints(repo).begin(active, content(), identity())
    repo.fail(active, SourceError('worker_lost', 'Fixture lost worker.', transient=True))
    make_due(repo, item)
    class Changed:
        def ready(self, language): raise AssertionError('Must not replace stored identity')
        def extract(self, data, *, expected_identity):
            assert expected_identity == identity()
            raise VisualError('visual_profile_changed')
    monkeypatch.setattr(visual_processing, 'build_visual_provider', lambda settings: Changed())
    assert not process(repo, item)
    assert repo.get_job(*scope(item)).failure_code == 'visual_profile_changed'
    assert cleanup_once(repo) == 1


@pytest.mark.parametrize('corrupt', ['foreign_key', 'bytes'])
def test_original_integrity_is_checked_before_native_call(ingestion, provider, corrupt):
    repo = ingestion[0]
    item = register_video(ingestion)
    if corrupt == 'foreign_key':
        with repo.store._connect() as connection:
            connection.execute("UPDATE video_inputs SET object_key='foreign/raw.mp4' WHERE tenant_id=%s AND project_id=%s AND job_id=%s", scope(item))
        repo.artifacts.fail_get = True
    else:
        key = next(iter(repo.artifacts.objects))
        repo.artifacts.objects[key] = b'PRIVATE_BAD_INPUT'
    assert not process(repo, item)
    assert repo.get_job(*scope(item)).failure_code == 'artifact_integrity'
    assert not provider.calls


def test_prepare_rolls_back_usage_completion_and_retirement_if_wall_clock_lease_expires(ingestion, monkeypatch):
    from app.sources import video
    repo = ingestion[0]
    item = register_video(ingestion)
    active = claim(repo, item)
    checkpoints = VisualCheckpoints(repo)
    checkpoints.begin(active, content(), identity())
    checkpoints.save(active, result())
    retire = video.retire_video
    def slow_retire(connection, *args):
        value = retire(connection, *args)
        connection.execute('SELECT pg_sleep(1)')
        return value
    monkeypatch.setattr(video, 'retire_video', slow_retire)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=clock_timestamp()+interval '500 milliseconds' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(item))
    assert not VideoRepository(repo).prepare(active)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 0
        assert connection.execute('SELECT prepared_at FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['prepared_at'] is None
        assert connection.execute('SELECT cleanup_id FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['cleanup_id'] is None
    assert repo.get_job(*scope(item)).status == 'running'


def test_raw_cleanup_fk_rejects_another_project_ticket_and_owner_can_observe_exhaustion(ingestion):
    import psycopg
    repo, service, principal, project, actor = ingestion
    item = register_video(ingestion)
    other = service.create_project(principal, ProjectCreate(title='Other cleanup scope'))
    ticket = service.delete_project(principal, other.id)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute('UPDATE video_inputs SET cleanup_id=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (ticket, *scope(item)))
    assert cleanup_once(repo) == 1  # Empty other-project ticket, never this input.
    repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'exhaustion-video-cancel')
    with repo.store._connect() as connection:
        cleanup = connection.execute('SELECT cleanup_id FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['cleanup_id']
        connection.execute('UPDATE artifact_cleanup SET attempt_count=5 WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id, project.id, cleanup))
    repo.artifacts.fail_delete = True
    assert cleanup_once(repo) == 0
    assert repo.get_cleanup(principal.tenant_id, project.id, cleanup, actor).status == 'failed'
    with pytest.raises(ProjectNotFoundError): repo.get_cleanup(principal.tenant_id, other.id, cleanup, actor)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT deleted_at FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()['deleted_at'] is None
