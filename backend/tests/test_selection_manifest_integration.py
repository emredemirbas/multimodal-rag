"""Actual DB/storage coordinators, synthetic v2 producer; no native activation."""
from concurrent.futures import ThreadPoolExecutor
import logging

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.chat.repository import ChatRepository
from app.jobs.dispatch import cleanup_once
from app.sources.contracts import SourceError
from app.sources.video import VideoRepository
from app.vision.checkpoints import VisualCheckpoints
from app.vision.gallery import VisualGalleryRepository
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import register_video, claim
from test_visual_checkpoints_integration import saved, scope, seed, claim_for
from test_visual_gallery_integration import deliver
from test_visual_index_integration import queue_index, run
from test_visual_selection import change_result
from test_visual_service import identity, result

pytestmark = pytest.mark.integration


def test_max_scan_and_concurrent_complete_save_keep_one_immutable_result(ingestion):
    source, job, data = seed(ingestion)
    active, checkpoints = claim_for(ingestion, source, job), VisualCheckpoints(ingestion[0])
    snapshot = change_result(600, [0, 255] * 300)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cursors = list(pool.map(lambda _: checkpoints.begin(active, data, snapshot.identity), range(2)))
    assert all(not cursor.result_saved for cursor in cursors)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: checkpoints.save(active, snapshot), range(2)))
    assert sorted(outcomes) == [False, True]
    assert checkpoints.load(active) == snapshot.result()
    assert checkpoints.begin(active, data, snapshot.identity).saved_frames == 20


def test_selection_checkpoint_survives_lease_recovery_without_reselection_or_content_logs(ingestion, caplog):
    caplog.set_level(logging.INFO, logger='tutorial_workspace.jobs')
    snapshot = change_result()
    active, checkpoints, data = saved(ingestion, snapshot)
    repo = ingestion[0]
    assert checkpoints.load(active) == snapshot.result()
    assert not checkpoints.save(active, snapshot)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(active))
    assert repo.recover_leases() == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(active))
    resumed = claim_for(ingestion, active['source_id'], active['id'])
    assert checkpoints.begin(resumed, data, snapshot.identity).saved_frames == 6
    assert checkpoints.load(resumed) == snapshot.result()
    assert checkpoints.load(active) is None
    with pytest.raises(SourceError): checkpoints.begin(resumed, data, identity())
    assert 'PRIVATE_OCR' not in caplog.text and snapshot.selection.samples[0].thumbnail_sha256 not in caplog.text
    assert '"selection_scan_samples": 20' in caplog.text


@pytest.mark.parametrize('corrupt', ['hash', 'score', 'ranking', 'missing_samples', 'version'])
def test_tampering_even_unselected_scan_metadata_fails_integrity(ingestion, corrupt):
    active, checkpoints, _ = saved(ingestion, change_result())
    with ingestion[0].store._connect() as connection:
        where = ' WHERE tenant_id=%s AND project_id=%s AND job_id=%s'
        manifest = connection.execute('SELECT selection_manifest FROM visual_runs' + where, scope(active)).fetchone()['selection_manifest']
        if corrupt == 'hash': manifest['samples'][1]['thumbnail_sha256'] = 'f' * 64
        elif corrupt == 'score': manifest['samples'][1]['mean_absolute_difference_ppm'] = 1  # Feasible but digest must change.
        elif corrupt == 'ranking': manifest['selected_timestamps_ms'][1] = 2000
        elif corrupt == 'missing_samples': manifest['samples'].pop()
        else: manifest['schema_version'] = 'unknown'
        connection.execute('UPDATE visual_runs SET selection_manifest=%s' + where, (Jsonb(manifest), *scope(active)))
    with pytest.raises(SourceError) as failure: checkpoints.load(active)
    assert failure.value.code == 'invalid_visual_checkpoint'


def test_missing_oversized_or_v1_manifests_fail_at_the_database_boundary(ingestion):
    old, _, _ = saved(ingestion)
    active, _, _ = saved(ingestion, change_result())
    for parameters in [(None, *scope(active)), (Jsonb({'private': 'x' * 196608}), *scope(active)),
                       (Jsonb(change_result().selection.model_dump()), *scope(old))]:
        with pytest.raises(psycopg.errors.CheckViolation):
            with ingestion[0].store._connect() as connection:
                connection.execute('UPDATE visual_runs SET selection_manifest=%s WHERE tenant_id=%s AND project_id=%s AND job_id=%s', parameters)


def test_final_fence_rolls_back_manifest_frames_and_digest_together(ingestion, monkeypatch):
    source, job, data = seed(ingestion)
    active, checkpoints, snapshot = claim_for(ingestion, source, job), VisualCheckpoints(ingestion[0]), change_result()
    checkpoints.begin(active, data, snapshot.identity)
    live, calls = checkpoints._live, []
    def lose_after_write(connection, claim):
        calls.append(1)
        return live(connection, claim) if len(calls) == 1 else None
    monkeypatch.setattr(checkpoints, '_live', lose_after_write)
    assert not checkpoints.save(active, snapshot)
    with ingestion[0].store._connect() as connection:
        row = connection.execute('SELECT saved_at,selection_manifest,result_sha256 FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(active)).fetchone()
        assert row == {'saved_at': None, 'selection_manifest': None, 'result_sha256': None}
        assert connection.execute('SELECT count(*) AS n FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(active)).fetchone()['n'] == 0


def test_0017_shaped_legacy_snapshot_upgrades_without_rewriting_digest_or_frames(ingestion):
    active, checkpoints, _ = saved(ingestion)
    store = ingestion[0].store
    with store._connect() as connection:
        before = connection.execute('SELECT * FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(active)).fetchone()
        frames = connection.execute('SELECT * FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s ORDER BY ordinal', scope(active)).fetchall()
        # Reconstruct exactly the pre-0018 constraints/columns in this disposable schema.
        connection.execute('ALTER TABLE visual_runs DROP CONSTRAINT visual_runs_selection_version_check')
        connection.execute('ALTER TABLE visual_runs DROP COLUMN selection_manifest')
        connection.execute('ALTER TABLE visual_runs DROP CONSTRAINT visual_runs_profile_check')
        connection.execute("ALTER TABLE visual_runs ADD CONSTRAINT visual_runs_profile_check CHECK (profile ~ '^local-visual-v1:[a-f0-9]{64}$')")
        connection.execute("DELETE FROM schema_migrations WHERE version='0018_visual_selection_manifest.sql'")
    store.run_migrations()
    store.run_migrations()
    with store._connect() as connection:
        after = connection.execute('SELECT * FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(active)).fetchone()
        assert after == before
        assert connection.execute('SELECT * FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s ORDER BY ordinal', scope(active)).fetchall() == frames
    assert checkpoints.load(active) == result()


def test_temporal_return_gallery_index_old_evidence_and_project_deletion(ingestion):
    repo, service, principal, project, actor = ingestion
    snapshot = change_result()
    original = register_video(ingestion)
    active = claim(repo, original)
    checkpoints = VisualCheckpoints(repo)
    from test_visual_service import content
    checkpoints.begin(active, content(), snapshot.identity)
    assert checkpoints.save(active, snapshot)
    assert VideoRepository(repo).prepare(active)
    assert cleanup_once(repo) == 1
    galleries = VisualGalleryRepository(repo)
    publication = galleries.enqueue(principal.tenant_id, project.id, original.source.id, original.job.id, actor, 'retain-change-fixture')
    for index in range(6):
        make_due(repo, publication)
        assert deliver(repo, publication) is (index == 5)
    view = galleries.gallery(principal.tenant_id, project.id, original.source.id, actor)
    assert [frame.timestamp_ms for frame in view.items] == snapshot.selection.selected_timestamps_ms
    assert view.origin.profile == snapshot.identity.profile and view.origin.checkpoint_version == 'visual-checkpoint-v2'
    public = view.model_dump_json()
    assert 'thumbnail_sha256' not in public and 'selection_manifest' not in public
    assert galleries.image(principal.tenant_id, project.id, view.items[0].id, actor) == galleries.image(principal.tenant_id, project.id, view.items[2].id, actor)
    item = queue_index(ingestion, publication)
    assert run(repo, item)
    response = service.ask(principal, project.id, 'user_id')
    assert not response.abstained and response.citations
    citation = response.citations[0]
    assert citation.visual_origin.profile == snapshot.identity.profile
    evidence = ChatRepository(repo.store).evidence(principal.tenant_id, project.id, actor, citation.segment_id)
    assert evidence.visual_origin == citation.visual_origin
    assert run(repo, queue_index(ingestion, publication, 'reindex-change-fixture'))
    assert ChatRepository(repo.store).evidence(principal.tenant_id, project.id, actor, citation.segment_id) == evidence
    with repo.store._connect() as connection:
        usage = connection.execute('SELECT model,selected_frame_count,billed_usd FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id, project.id, original.job.id)).fetchone()
        assert usage['model'] == snapshot.identity.profile and usage['selected_frame_count'] == 6 and usage['billed_usd'] == 0
    service.delete_project(principal, project.id)
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    with repo.store._connect() as connection:
        for table in ['visual_runs', 'visual_checkpoint_frames', 'retained_visual_frames', 'content_segments', 'processing_versions']:
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['n'] == 0
