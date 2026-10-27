"""Actual DB/outbox handoffs, explicit fixture-only MP4/PNG/OCR/embeddings."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import logging
from uuid import uuid4

import psycopg
import pytest

from app.embedding_profiles import HASH_SPACE, QWEN_SPACE
from app.jobs.dispatch import cleanup_once
from app.jobs.visual_indexing import index_visual
from app.models import AuthenticatedPrincipal
from app.sources.contracts import Registration, SourceError
from app.sources.video import VideoRepository
from app.vision import workflow
from app.vision.checkpoints import VisualCheckpoints
from app.vision.gallery import VisualGalleryRepository
from app.vision.index import VisualIndexRepository
from test_checkpoints_integration import make_due
from test_embedding_spaces_integration import FixtureSemanticProvider
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import register_video, claim, process, provider
from test_visual_gallery_integration import deliver
from test_visual_service import content, identity, result

pytestmark = pytest.mark.integration


def accepted(ingestion, **overrides):
    return register_video(ingestion, auto_process=True, **overrides)


def saved(ingestion):
    item = accepted(ingestion)
    active = claim(ingestion[0], item)
    checkpoints = VisualCheckpoints(ingestion[0])
    checkpoints.begin(active, content(), identity())
    assert checkpoints.save(active, result())
    return item, active


def latest(ingestion, item):
    repo, _, principal, project, _ = ingestion
    source = repo.get_source(principal.tenant_id, project.id, item.source.id)
    return Registration(source=source, job=source.job)


def publication(ingestion):
    item, active = saved(ingestion)
    assert VideoRepository(ingestion[0]).prepare(active)
    return item, latest(ingestion, item)


def indexed_job(ingestion):
    original, item = publication(ingestion)
    assert not deliver(ingestion[0], item)
    make_due(ingestion[0], item)
    assert deliver(ingestion[0], item)
    return original, latest(ingestion, item)


def run(repo, item):
    return index_visual(repo, item.source.tenant_id, item.source.project_id, item.source.id, item.job.id, item.job.generation)


def row(ingestion, source):
    repo, _, principal, project, _ = ingestion
    with repo.store._connect() as connection:
        return connection.execute('SELECT * FROM video_workflows WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                  (principal.tenant_id, project.id, source)).fetchone()


def test_automatic_pipeline_replays_original_receipt_and_counts_usage_once(ingestion, provider, caplog):
    repo, service, principal, project, actor = ingestion
    caplog.set_level(logging.INFO, logger='tutorial_workspace.jobs')
    with ThreadPoolExecutor(max_workers=2) as pool:
        items = list(pool.map(lambda _: accepted(ingestion), range(2)))
    original = items[0]
    assert items[1].source.id == original.source.id and sum(i.deduplicated for i in items) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: process(repo, original), range(2))) == [False, True]
    item = latest(ingestion, original)
    assert item.job.job_type == 'visual_publish' and item.job.generation == 2 and item.source.status == 'processing'
    assert row(ingestion, original.source.id)['publication_job_id'] == item.job.id
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert not deliver(repo, item)
    make_due(repo, item)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: deliver(repo, item), range(2))) == [False, True]
    index = latest(ingestion, item)
    assert index.job.job_type == 'visual_index' and index.job.generation == 3 and index.source.status == 'indexing'
    assert row(ingestion, original.source.id)['index_job_id'] == index.job.id
    assert service.ask(principal, project.id, 'user_id').abstained
    assert run(repo, index) and not run(repo, index)
    current = latest(ingestion, index)
    assert current.source.status == 'ready' and current.source.active_generation == 3
    citation = service.ask(principal, project.id, 'user_id').citations[0]
    assert citation.visual_origin.job_id == original.job.id and citation.frame_id
    assert provider.calls == ['ready', 'extract']
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    replay = accepted(ingestion)
    assert replay.deduplicated and replay.job.id == original.job.id and replay.source.generation == 3
    assert row(ingestion, original.source.id)['target_embedding_space'] == HASH_SPACE
    assert len(repo.artifacts.objects) == 2
    with pytest.raises(SourceError) as error: register_video(ingestion)  # Manual/automatic is part of identity.
    assert error.value.code == 'idempotency_conflict'
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM processing_jobs').fetchone()['n'] == 3
        assert connection.execute('SELECT count(*) AS n FROM outbox_events').fetchone()['n'] == 3
        usage = connection.execute('SELECT * FROM usage_events ORDER BY generation').fetchall()
        assert len(usage) == 2 and usage[0]['input_video_bytes'] == len(content())
        assert usage[0]['selected_frame_count'] == 2 and usage[1]['segment_count'] == 2
        assert all(u['billed_usd'] == 0 for u in usage)
    assert 'video_gallery_queued' in caplog.text and '"index_queued": true' in caplog.text
    assert 'PRIVATE_OCR' not in caplog.text and 'owned.mp4' not in caplog.text


@pytest.mark.parametrize('mode', [None, 'true', 1])
def test_non_boolean_mode_never_writes_or_fetches(ingestion, mode):
    with pytest.raises(SourceError) as error: register_video(ingestion, auto_process=mode)
    assert error.value.code == 'invalid_video_workflow' and not ingestion[0].artifacts.objects


def test_manual_registration_is_not_silently_upgraded(ingestion):
    item = register_video(ingestion)
    assert row(ingestion, item.source.id) is None
    with pytest.raises(SourceError) as error: accepted(ingestion)
    assert error.value.code == 'idempotency_conflict'


@pytest.mark.parametrize('repository', [VisualGalleryRepository, VisualIndexRepository])
def test_continuation_requires_an_existing_parent_transaction(ingestion, repository):
    repo, _, principal, project, actor = ingestion
    with pytest.raises(ValueError):
        repository(repo).enqueue(principal.tenant_id, project.id, uuid4(), uuid4(), actor,
                                 'standalone-continuation', continuation=True)


def test_blank_ocr_retains_inspectable_gallery_without_inventing_search_evidence(ingestion):
    repo, service, principal, project, actor = ingestion
    original = accepted(ingestion)
    active = claim(repo, original)
    baseline = result()
    blank = replace(baseline, frames=tuple(frame.model_copy(update={'text': ''}) for frame in baseline.frames))
    checkpoints = VisualCheckpoints(repo)
    checkpoints.begin(active, content(), identity())
    assert checkpoints.save(active, blank) and VideoRepository(repo).prepare(active)
    pub = latest(ingestion, original)
    assert not deliver(repo, pub)
    make_due(repo, pub)
    assert deliver(repo, pub)
    item = latest(ingestion, pub)
    assert not run(repo, item)
    current = latest(ingestion, item)
    assert current.job.failure_code == 'visual_ocr_empty' and current.source.active_generation is None
    gallery = VisualGalleryRepository(repo).gallery(principal.tenant_id, project.id, item.source.id, actor)
    assert len(gallery.items) == 2 and not gallery.searchable
    assert service.ask(principal, project.id, 'user_id').abstained
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM content_segments').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 1


@pytest.mark.parametrize('stage', ['preparation', 'publication'])
def test_child_outbox_and_parent_completion_roll_back_together(ingestion, monkeypatch, stage):
    repo, _, principal, project, _ = ingestion
    if stage == 'preparation':
        item, active = saved(ingestion)
        target, callback = VisualGalleryRepository, VideoRepository(repo).prepare
    else:
        _, item = publication(ingestion)
        assert not deliver(repo, item)
        make_due(repo, item)
        active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
        target, callback = VisualIndexRepository, VisualGalleryRepository(repo).adopt_next
    enqueue = target.enqueue
    def interrupted(self, *args, **kwargs):
        enqueue(self, *args, **kwargs)
        raise RuntimeError('fixture interrupted after child/outbox creation')
    with monkeypatch.context() as patch:
        patch.setattr(target, 'enqueue', interrupted)
        with pytest.raises(RuntimeError): callback(active)
    current = latest(ingestion, item)
    assert current.job.id == item.job.id and current.job.status == 'running'
    value = row(ingestion, item.source.id)
    assert value['publication_job_id' if stage == 'preparation' else 'index_job_id'] is None
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM processing_jobs').fetchone()['n'] == item.job.generation
        assert connection.execute('SELECT count(*) AS n FROM outbox_events').fetchone()['n'] == item.job.generation
        if stage == 'preparation':
            assert connection.execute('SELECT cleanup_id FROM video_inputs').fetchone()['cleanup_id'] is None
            assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 0
            assert connection.execute('SELECT prepared_at FROM visual_runs').fetchone()['prepared_at'] is None
        else:
            assert connection.execute('SELECT published_at FROM visual_publications').fetchone()['published_at'] is None
            assert connection.execute('SELECT count(*) AS n FROM retained_visual_frames').fetchone()['n'] == 1
    assert callback(active)  # Committed inference/frame progress is sufficient; no new provider.
    assert latest(ingestion, item).job.generation == item.job.generation + 1
    while cleanup_once(repo): pass
    if stage == 'publication': assert len(repo.artifacts.objects) == 2  # Failed unique candidate cleaned only.


@pytest.mark.parametrize('stage', ['preparation', 'publication'])
def test_final_wall_clock_expiry_rolls_back_even_an_already_created_child(ingestion, monkeypatch, stage):
    repo, _, principal, project, _ = ingestion
    if stage == 'preparation':
        item, active = saved(ingestion)
        name, callback = 'after_preparation', VideoRepository(repo).prepare
    else:
        _, item = publication(ingestion)
        assert not deliver(repo, item)
        make_due(repo, item)
        active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
        name, callback = 'after_publication', VisualGalleryRepository(repo).adopt_next
    advance = getattr(workflow, name)
    def slow(repository, connection, claim):
        value = advance(repository, connection, claim)
        connection.execute('SELECT pg_sleep(1)')
        return value
    monkeypatch.setattr(workflow, name, slow)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=clock_timestamp()+interval '500 milliseconds' WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, item.job.id))
    assert not callback(active)
    assert latest(ingestion, item).job.id == item.job.id
    value = row(ingestion, item.source.id)
    assert value['publication_job_id' if stage == 'preparation' else 'index_job_id'] is None
    assert repo.recover_leases() == 1
    make_due(repo, item)
    monkeypatch.setattr(workflow, name, advance)
    if stage == 'preparation': assert process(repo, item)
    else: assert deliver(repo, item)
    assert latest(ingestion, item).job.generation == item.job.generation + 1


@pytest.mark.parametrize('stage', ['preparation', 'publication'])
@pytest.mark.parametrize('fence', ['tenant_id', 'project_id', 'source_id', 'generation', 'lease_token', 'actor_user_id', 'revoked'])
def test_automatic_transition_preserves_full_scope_and_authorization_fences(ingestion, stage, fence):
    repo, _, principal, project, actor = ingestion
    if stage == 'preparation':
        item, active = saved(ingestion)
        callback = VideoRepository(repo).prepare
    else:
        _, item = publication(ingestion)
        active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
        callback = VisualGalleryRepository(repo).adopt_next
    if fence == 'revoked':
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    else: active[fence] = 'foreign' if fence == 'tenant_id' else 999 if fence == 'generation' else uuid4()
    assert not callback(active)
    assert row(ingestion, item.source.id)['publication_job_id' if stage == 'preparation' else 'index_job_id'] is None
    assert latest(ingestion, item).job.id == item.job.id


@pytest.mark.parametrize('stage', ['extraction', 'gallery', 'index'])
def test_cancel_stops_handoff_and_only_original_actor_can_retry_derived_work(ingestion, stage):
    repo, _, principal, project, actor = ingestion
    if stage == 'extraction': item, active = saved(ingestion)
    elif stage == 'gallery': _, item = publication(ingestion)
    else: _, item = indexed_job(ingestion)
    if stage == 'gallery': assert not deliver(repo, item)
    repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'workflow-cancel-fixture')
    if stage == 'extraction':
        assert not VideoRepository(repo).prepare(active)
        with pytest.raises(SourceError) as error:
            repo.command(principal.tenant_id, project.id, item.source.id, actor, 'retry', 'workflow-extraction-retry')
        assert error.value.code == 'video_reupload_required'
        assert row(ingestion, item.source.id)['publication_job_id'] is None
        return
    assert not deliver(repo, item) if stage == 'gallery' else not run(repo, item)
    other = repo.store.bootstrap_principal(AuthenticatedPrincipal(provider='test', subject='workflow-other', tenant_id=principal.tenant_id))
    with pytest.raises(SourceError) as error:
        repo.command(principal.tenant_id, project.id, item.source.id, other, 'retry', 'other-workflow-retry')
    assert error.value.code == 'visual_initiator_required'
    assert latest(ingestion, item).job.status == 'cancelled'
    retry = repo.command(principal.tenant_id, project.id, item.source.id, actor, 'retry', 'workflow-derived-retry')
    while cleanup_once(repo): pass
    repo.artifacts.fail_get = True  # Derived handoff must not read the retired MP4.
    if stage == 'gallery':
        assert deliver(repo, retry)
        item = latest(ingestion, item)
    assert run(repo, item)
    assert latest(ingestion, item).source.status == 'ready'


def test_existing_accepted_work_continues_through_archive_without_new_manual_commands(ingestion):
    repo, service, principal, project, actor = ingestion
    item, active = saved(ingestion)
    service.archive_project(principal, project.id)
    with pytest.raises(SourceError): accepted(ingestion, idempotency_key='archived-new-video')
    assert VideoRepository(repo).prepare(active)
    pub = latest(ingestion, item)
    with pytest.raises(SourceError):
        VisualGalleryRepository(repo).enqueue(principal.tenant_id, project.id, item.source.id, item.job.id, actor, 'manual-archived-gallery')
    assert not deliver(repo, pub)
    make_due(repo, pub)
    assert deliver(repo, pub)
    index = latest(ingestion, item)
    assert run(repo, index)
    assert VisualGalleryRepository(repo).gallery(principal.tenant_id, project.id, item.source.id, actor).searchable


def test_registration_pins_embedding_target_not_visual_worker_configuration(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    original, active = saved(ingestion)
    repo.settings = replace(repo.settings, embedding_provider='hash')  # Visual coordinator default differs.
    assert VideoRepository(repo).prepare(active)
    pub = latest(ingestion, original)
    assert not deliver(repo, pub)
    make_due(repo, pub)
    assert deliver(repo, pub)
    item = latest(ingestion, pub)
    with repo.store._connect() as connection:
        target = connection.execute('SELECT target_embedding_space FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND id=%s',
                                    (principal.tenant_id, project.id, item.job.id)).fetchone()['target_embedding_space']
    assert target == QWEN_SPACE and row(ingestion, item.source.id)['target_embedding_space'] == QWEN_SPACE
    assert not run(repo, item)
    assert latest(ingestion, item).job.failure_code == 'processing_configuration_changed'
    assert latest(ingestion, item).source.active_generation is None
    provider = FixtureSemanticProvider()
    monkeypatch.setattr('app.jobs.visual_indexing.build_embedding_provider', lambda _: provider)
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    repo.command(principal.tenant_id, project.id, item.source.id, actor, 'retry', 'matching-mode-workflow-retry')
    assert run(repo, item)
    assert latest(ingestion, item).source.active_embedding_space == QWEN_SPACE


@pytest.mark.parametrize('operation', ['source', 'project'])
@pytest.mark.parametrize('stage', ['preparation', 'publication', 'indexed'])
def test_complete_deletion_removes_workflow_jobs_evidence_and_objects(ingestion, operation, stage):
    repo, service, principal, project, actor = ingestion
    if stage == 'preparation': item, active = saved(ingestion)
    elif stage == 'publication': _, item = publication(ingestion)
    else:
        _, item = indexed_job(ingestion)
        assert run(repo, item)
    if operation == 'source': repo.delete_source(principal.tenant_id, project.id, item.source.id, actor)
    else: service.delete_project(principal, project.id)
    while cleanup_once(repo): pass
    assert not repo.artifacts.objects
    with repo.store._connect() as connection:
        for table in ('video_workflows', 'video_inputs', 'visual_runs', 'visual_checkpoint_frames', 'visual_publications',
                      'retained_visual_frames', 'visual_index_runs', 'visual_index_chunks', 'processing_versions', 'content_segments'):
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s',
                                      (principal.tenant_id, project.id)).fetchone()['n'] == 0


@pytest.mark.parametrize('relationship', ['origin', 'publication', 'index'])
def test_workflow_foreign_keys_cannot_adopt_other_source_identities(ingestion, relationship):
    repo = ingestion[0]
    original, item = indexed_job(ingestion)
    other = accepted(ingestion, idempotency_key='another-workflow-fixture')
    if relationship == 'index':
        active = claim(repo, other)
        checkpoints = VisualCheckpoints(repo)
        checkpoints.begin(active, content(), identity())
        checkpoints.save(active, result())
        assert VideoRepository(repo).prepare(active)
    original_row = row(ingestion, original.source.id)
    fields = {'origin': ('visual_job_id', 'visual_generation'), 'publication': ('publication_job_id', 'publication_generation'),
              'index': ('index_job_id', 'index_generation')}[relationship]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute(f'UPDATE video_workflows SET {fields[0]}=%s,{fields[1]}=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                (original_row[fields[0]], original_row[fields[1]], other.source.tenant_id, other.source.project_id, other.source.id))
