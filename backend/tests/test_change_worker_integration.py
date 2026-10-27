from dataclasses import replace

import pytest

from app.jobs import visual_processing
from app.vision.checkpoints import VisualCheckpoints
from test_change_service import change_identity
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_video_integration import register_video, claim, process, scope
from test_visual_selection import change_result
from test_visual_service import content, identity, result

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('pinned', ['uniform', 'change'])
@pytest.mark.parametrize('saved', [False, True])
def test_recovery_uses_pinned_policy_after_configuration_changes(ingestion, monkeypatch, pinned, saved):
    repo = ingestion[0]
    item = register_video(ingestion)
    active = claim(repo, item)
    checkpoints = VisualCheckpoints(repo)
    snapshot = change_result().result() if pinned == 'change' else result()
    pin = change_identity() if pinned == 'change' else identity()
    checkpoints.begin(active, content(), pin)
    if saved: assert checkpoints.save(active, snapshot)
    with repo.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", scope(item))
    assert repo.recover_leases() == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope(item))
    repo.settings = replace(repo.settings, visual_selection='uniform' if pinned == 'change' else 'change')
    calls = []
    class Provider:
        def ready(self, *args, **kwargs): pytest.fail('Must not repin a generation')
        def extract(self, data, *, expected_identity):
            calls.append('extract')
            assert expected_identity == pin
            return snapshot
    monkeypatch.setattr(visual_processing, 'build_visual_provider', lambda settings: Provider())
    assert process(repo, item)
    assert calls == ([] if saved else ['extract'])
    with repo.store._connect() as connection:
        row = connection.execute('SELECT profile FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope(item)).fetchone()
        assert row['profile'] == pin.profile


@pytest.mark.parametrize('selection', ['uniform', 'change'])
def test_new_unpinned_jobs_use_explicit_worker_selection(ingestion, monkeypatch, selection):
    repo = ingestion[0]
    repo.settings = replace(repo.settings, visual_selection=selection)
    pin = change_identity() if selection == 'change' else identity()
    calls = []
    class Provider:
        def ready(self, language, **kwargs):
            calls.append(kwargs)
            assert language == 'en' and kwargs == ({'selection': 'change'} if selection == 'change' else {})
            return pin
        def extract(self, data, *, expected_identity):
            assert expected_identity == pin
            return change_result().result() if selection == 'change' else result()
    monkeypatch.setattr(visual_processing, 'build_visual_provider', lambda settings: Provider())
    assert process(repo, register_video(ingestion))
    assert len(calls) == 1
