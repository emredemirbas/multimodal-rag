"""Actual PostgreSQL, fixture-only inference; retained inspection is not RAG."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.auth import DevelopmentAuthenticator
from app.jobs.dispatch import cleanup_once
from app.jobs.visual_publication import publish_visual
from app.main import create_app
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.sources.video import VideoRepository
from app.store import ProjectNotFoundError
from app.vision.checkpoints import VisualCheckpoints
from app.vision.gallery import VisualGalleryRepository
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import register_video, claim
from test_visual_service import content, identity, result

pytestmark = pytest.mark.integration


def prepared(ingestion, snapshot=None):
    repo = ingestion[0]
    item = register_video(ingestion)
    active = claim(repo, item)
    checkpoint = VisualCheckpoints(repo)
    checkpoint.begin(active, content(), identity())
    checkpoint.save(active, snapshot or result())
    assert VideoRepository(repo).prepare(active)
    assert cleanup_once(repo) == 1
    return item


def queue(ingestion):
    original = prepared(ingestion)
    repo, _, principal, project, actor = ingestion
    publication = VisualGalleryRepository(repo).enqueue(principal.tenant_id, project.id, original.source.id,
        original.job.id, actor, 'retain-frames-fixture')
    return original, publication


def deliver(repo, item):
    return publish_visual(repo, item.source.tenant_id, item.source.project_id, item.source.id, item.job.id, item.job.generation)


def complete(ingestion):
    original, item = queue(ingestion)
    assert not deliver(ingestion[0], item)
    make_due(ingestion[0], item)
    assert deliver(ingestion[0], item)
    return original, item


def test_one_frame_per_delivery_private_until_atomic_gallery_completion_and_no_index(ingestion):
    repo, service, principal, project, actor = ingestion
    original, item = queue(ingestion)
    gallery = VisualGalleryRepository(repo)
    assert gallery.gallery(principal.tenant_id, project.id, item.source.id, actor).items == []
    assert not deliver(repo, item)
    assert gallery.gallery(principal.tenant_id, project.id, item.source.id, actor).items == []
    with repo.store._connect() as connection:
        frame = connection.execute('SELECT id FROM retained_visual_frames').fetchone()['id']
    with pytest.raises(ProjectNotFoundError): gallery.image(principal.tenant_id, project.id, frame, actor)
    assert len(repo.artifacts.objects) == 1
    make_due(repo, item)
    assert deliver(repo, item) and not deliver(repo, item)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    assert len(view.items) == 2 and view.generation == 2 and not view.searchable
    assert view.origin.job_id == original.job.id and view.origin.generation == 1
    assert not view.origin.human_reviewed and view.origin.language == 'en'
    assert view.items[0].ocr_text == result().frames[0].text
    assert gallery.image(principal.tenant_id, project.id, view.items[0].id, actor) == result().frames[0].image
    current = repo.get_source(principal.tenant_id, project.id, item.source.id)
    assert current.frame_count == 2 and current.active_generation is None and current.segment_count == 0
    assert current.status == 'metadata_ready' and current.job.stage == 'frames_retained'
    assert current.job.delivery_count == 2 and current.job.attempt_count == 1
    assert service.ask(principal, project.id, 'GET /health').abstained
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n'] == 1
        assert connection.execute('SELECT count(*) AS n FROM processing_versions').fetchone()['n'] == 0
    assert 'tutorial_visual_galleries{status="published"} 1\n' in repo.render_metrics()


def test_concurrent_private_enqueue_and_duplicate_delivery_accept_once(ingestion):
    original = prepared(ingestion)
    repo, _, principal, project, actor = ingestion
    gallery = VisualGalleryRepository(repo)
    with ThreadPoolExecutor(max_workers=2) as pool:
        items = list(pool.map(lambda _: gallery.enqueue(principal.tenant_id, project.id, original.source.id,
            original.job.id, actor, 'retain-concurrent-fixture'), range(2)))
    assert items[0].job.id == items[1].job.id
    assert sorted(item.deduplicated for item in items) == [False, True]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: deliver(repo, items[0]), range(2))) == [False, False]
    assert len(repo.artifacts.objects) == 1
    make_due(repo, items[0])
    assert deliver(repo, items[0])
    replay = gallery.enqueue(principal.tenant_id, project.id, original.source.id, original.job.id, actor, 'another-retain-fixture')
    assert replay.deduplicated and replay.job.id == items[0].job.id and len(repo.artifacts.objects) == 2


def test_adoption_can_follow_raw_deletion_and_expired_original_eligibility(ingestion):
    repo = ingestion[0]
    _, item = queue(ingestion)
    with repo.store._connect() as connection:
        connection.execute("UPDATE video_inputs SET expires_at=now()-interval '1 hour'")
    assert not deliver(repo, item)
    make_due(repo, item)
    assert deliver(repo, item)
    assert all(key.endswith('/frame.png') for key in repo.artifacts.objects)


@pytest.mark.parametrize('boundary', ['enqueue', 'gallery', 'image'])
def test_foreign_tenant_project_actor_and_deleted_scope_are_rejected(ingestion, boundary):
    repo, service, principal, project, actor = ingestion
    original, item = complete(ingestion)
    gallery = VisualGalleryRepository(repo)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    for tenant, project_id, user in [('foreign', project.id, actor), (principal.tenant_id, uuid4(), actor), (principal.tenant_id, project.id, uuid4())]:
        with pytest.raises(ProjectNotFoundError):
            if boundary == 'enqueue': gallery.enqueue(tenant, project_id, item.source.id, original.job.id, user, 'foreign-gallery-key')
            elif boundary == 'gallery': gallery.gallery(tenant, project_id, item.source.id, user)
            else: gallery.image(tenant, project_id, view.items[0].id, user)
    service.delete_project(principal, project.id)
    with pytest.raises(ProjectNotFoundError): gallery.image(principal.tenant_id, project.id, view.items[0].id, actor)
    while cleanup_once(repo): pass
    assert not repo.artifacts.objects


@pytest.mark.parametrize('invalidate', ['revoke', 'lease', 'cancel', 'source', 'project', 'rollback'])
def test_post_put_invalidation_never_adopts_and_orphan_is_cleaned(ingestion, invalidate):
    repo, service, principal, project, actor = ingestion
    _, item = queue(ingestion)
    def after_put():
        if invalidate == 'rollback': raise RuntimeError('PRIVATE_STORAGE_DETAIL')
        if invalidate == 'cancel': repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'inflight-frame-cancel')
        elif invalidate == 'source': repo.delete_source(principal.tenant_id, project.id, item.source.id, actor)
        elif invalidate == 'project': service.delete_project(principal, project.id)
        else:
            with repo.store._connect() as connection:
                if invalidate == 'revoke': connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
                else: connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, item.job.id))
    # Project/job mutation in a second connection would wait for the adoption
    # lock. Inject into the active connection separately in dedicated fence tests.
    if invalidate in {'cancel', 'source', 'project', 'lease'}:
        if invalidate == 'cancel': repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'before-frame-cancel')
        elif invalidate == 'source': repo.delete_source(principal.tenant_id, project.id, item.source.id, actor)
        elif invalidate == 'project': service.delete_project(principal, project.id)
        else:
            active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
            with repo.store._connect() as connection:
                connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, item.job.id))
            assert not VisualGalleryRepository(repo).adopt_next(active)
        assert not deliver(repo, item)
    else:
        repo.artifacts.after_put = after_put
        assert not deliver(repo, item)
        assert repo.artifacts.objects
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM retained_visual_frames').fetchone()['n'] == 0
    while cleanup_once(repo): pass
    assert not repo.artifacts.objects


def test_cancel_retry_reuses_committed_frame_without_raw_resurrection(ingestion):
    repo, _, principal, project, actor = ingestion
    _, item = queue(ingestion)
    assert not deliver(repo, item)
    first_key = next(iter(repo.artifacts.objects))
    repo.command(principal.tenant_id, project.id, item.source.id, actor, 'cancel', 'cancel-gallery-fixture')
    retry = repo.command(principal.tenant_id, project.id, item.source.id, actor, 'retry', 'retry-gallery-fixture')
    assert deliver(repo, retry) and first_key in repo.artifacts.objects and len(repo.artifacts.objects) == 2
    with pytest.raises(SourceError): repo.command(principal.tenant_id, project.id, item.source.id, actor, 'reprocess', 'reprocess-gallery-fixture')


@pytest.mark.parametrize('corrupt', ['text', 'hash', 'key', 'missing', 'profile', 'object'])
def test_corrupt_manifest_and_image_fail_closed(ingestion, corrupt):
    repo, _, principal, project, actor = ingestion
    _, item = complete(ingestion)
    gallery = VisualGalleryRepository(repo)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    with repo.store._connect() as connection:
        if corrupt == 'text': connection.execute("UPDATE retained_visual_frames SET ocr_text='changed'")
        elif corrupt == 'hash': connection.execute("UPDATE retained_visual_frames SET image_sha256=repeat('a',64)")
        elif corrupt == 'key': connection.execute("UPDATE retained_visual_frames SET object_key='foreign/frame.png'")
        elif corrupt == 'missing': connection.execute('DELETE FROM retained_visual_frames WHERE ordinal=0')
        elif corrupt == 'profile': connection.execute("UPDATE visual_runs SET profile='local-visual-v1:'||repeat('a',64)")
    if corrupt == 'object':
        key = next(iter(repo.artifacts.objects))
        repo.artifacts.objects[key] = b'PRIVATE_BAD_PNG'
    with pytest.raises((SourceError, ProjectNotFoundError)): gallery.image(principal.tenant_id, project.id, view.items[0].id, actor)


def test_image_rechecks_authorization_after_storage_read_and_archive_is_readable(ingestion):
    repo, service, principal, project, actor = ingestion
    _, item = complete(ingestion)
    gallery = VisualGalleryRepository(repo)
    service.archive_project(principal, project.id)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    original_get = repo.artifacts.get
    def revoke(key, limit):
        data = original_get(key, limit)
        with repo.store._connect() as connection:
            connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
        return data
    repo.artifacts.get = revoke
    with pytest.raises(ProjectNotFoundError): gallery.image(principal.tenant_id, project.id, view.items[0].id, actor)


def test_authenticated_no_store_gallery_and_png_http_do_not_expose_keys(ingestion):
    repo, _, principal, project, actor = ingestion
    _, item = complete(ingestion)
    auth = DevelopmentAuthenticator(token='test-development-token', subject=principal.subject, tenant_id=principal.tenant_id)
    # Reuse the exact external identity provider to preserve the fixture actor.
    class FixtureAuth:
        def authenticate(self, headers):
            auth.authenticate(headers)
            return principal
    app = create_app(settings=replace(repo.settings, store_backend='postgres'), store=repo.store, artifacts=repo.artifacts, authenticator=FixtureAuth())
    with TestClient(app) as client:
        path = f'/api/v1/projects/{project.id}/sources/{item.source.id}/frames'
        assert client.get(path).status_code == 401
        headers = {'Authorization': 'Bearer test-development-token'}
        response = client.get(path, headers=headers)
        assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
        assert 'object_key' not in response.text and 'input_sha256' not in response.text
        frame = response.json()['items'][0]['id']
        image = client.get(f'/api/v1/projects/{project.id}/frames/{frame}/image', headers=headers)
        assert image.status_code == 200 and image.content == result().frames[0].image
        assert image.headers['content-type'] == 'image/png' and image.headers['x-content-type-options'] == 'nosniff'
        assert 'no-store' in image.headers['cache-control']


def test_maximum_twenty_blank_ocr_frames_continue_without_consuming_retries(ingestion):
    import hashlib
    from app.vision.local import VisualResult
    from app.vision.media import FrameEvidence, VideoInfo, encode_png
    repo, _, principal, project, actor = ingestion
    snapshot = VisualResult(hashlib.sha256(content()).hexdigest(), VideoInfo(duration_ms=600000, width=16, height=16,
        fps_numerator=2, fps_denominator=1), identity().model_dump(), 20, tuple(FrameEvidence(sample_target_ms=i*30000,
        timestamp_ms=i*30000, width=16, height=16, image=encode_png(16,16,bytes([i])*256), text='') for i in range(20)))
    original = prepared(ingestion, snapshot)
    gallery = VisualGalleryRepository(repo)
    item = gallery.enqueue(principal.tenant_id, project.id, original.source.id, original.job.id, actor, 'twenty-frames-fixture')
    for index in range(20):
        make_due(repo, item)
        assert deliver(repo, item) == (index == 19)
    current = repo.get_job(principal.tenant_id, project.id, item.job.id)
    assert current.attempt_count == 1 and current.delivery_count == 20
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    assert len(view.items) == 20 and all(not frame.ocr_text for frame in view.items)


def test_wall_clock_expiry_after_put_rolls_back_reference_and_schedules_orphan(ingestion):
    import time
    repo, _, principal, project, _ = ingestion
    _, item = queue(ingestion)
    active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=clock_timestamp()+interval '500 milliseconds' WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, item.job.id))
    repo.artifacts.after_put = lambda: time.sleep(1)
    assert not VisualGalleryRepository(repo).adopt_next(active)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM retained_visual_frames').fetchone()['n'] == 0
    assert len(repo.artifacts.objects) == 1 and cleanup_once(repo) == 1 and not repo.artifacts.objects


def test_failed_candidate_cleanup_cannot_delete_later_adopted_frame(ingestion):
    repo, _, principal, project, actor = ingestion
    _, item = queue(ingestion)
    def interrupted(): raise RuntimeError('PRIVATE_POST_PUT_FAILURE')
    repo.artifacts.after_put = interrupted
    assert not deliver(repo, item)
    orphan = next(iter(repo.artifacts.objects))
    repo.artifacts.after_put = None
    make_due(repo, item)
    assert not deliver(repo, item)
    make_due(repo, item)
    assert deliver(repo, item)
    assert len(repo.artifacts.objects) == 3
    assert cleanup_once(repo) == 1 and orphan not in repo.artifacts.objects and len(repo.artifacts.objects) == 2
    gallery = VisualGalleryRepository(repo)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, actor)
    assert gallery.image(principal.tenant_id, project.id, view.items[0].id, actor) == result().frames[0].image


@pytest.mark.parametrize('fence', ['tenant_id', 'project_id', 'source_id', 'generation', 'lease_token', 'actor_user_id'])
def test_adoption_checks_exact_scope_generation_token_and_initiator(ingestion, fence):
    repo, _, principal, project, _ = ingestion
    _, item = queue(ingestion)
    active = repo.claim_job(principal.tenant_id, project.id, item.source.id, item.job.id, 2, job_types=('visual_publish',))
    if fence == 'tenant_id': active[fence] = 'foreign'
    elif fence == 'generation': active[fence] = 999
    elif fence == 'actor_user_id': active[fence] = repo.store.bootstrap_principal(AuthenticatedPrincipal(provider='test', subject='another-member', tenant_id=principal.tenant_id))
    else: active[fence] = uuid4()
    assert not VisualGalleryRepository(repo).adopt_next(active)
    assert not repo.artifacts.objects


def test_publication_origin_fk_cannot_reference_another_source_run(ingestion):
    import psycopg
    from test_visual_checkpoints_integration import saved
    repo = ingestion[0]
    _, item = queue(ingestion)
    unrelated, _, _ = saved(ingestion)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with repo.store._connect() as connection:
            connection.execute('UPDATE visual_publications SET visual_job_id=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                               (unrelated['id'], item.source.tenant_id, item.source.project_id, item.job.id))


def test_inspection_follows_existing_tenant_membership_policy_not_original_actor_identity(ingestion):
    repo, _, principal, project, _ = ingestion
    _, item = complete(ingestion)
    member = repo.store.bootstrap_principal(AuthenticatedPrincipal(provider='test', subject='gallery-reader', tenant_id=principal.tenant_id))
    gallery = VisualGalleryRepository(repo)
    view = gallery.gallery(principal.tenant_id, project.id, item.source.id, member)
    assert gallery.image(principal.tenant_id, project.id, view.items[0].id, member) == result().frames[0].image


def test_unprepared_result_cannot_queue_publication_or_be_inspected(ingestion):
    repo, _, principal, project, actor = ingestion
    item = register_video(ingestion)
    gallery = VisualGalleryRepository(repo)
    with pytest.raises(SourceError) as error:
        gallery.enqueue(principal.tenant_id, project.id, item.source.id, item.job.id, actor, 'unprepared-gallery-key')
    assert error.value.code == 'visual_not_prepared'
    assert gallery.gallery(principal.tenant_id, project.id, item.source.id, actor).items == []
