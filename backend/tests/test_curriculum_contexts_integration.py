from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest

from app.curriculum.contracts import LearnerPreferences
from app.curriculum.persistence import ContextCreate, SourceSelection
from app.curriculum.repository import ContextRepository
from app.chat.repository import ChatRepository
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_ingestion_integration import ingestion, register, run
from test_postgres_integration import isolated_postgres_url
from test_frame_descriptions_integration import model as description_model
from test_frame_descriptions_integration import queue as queue_descriptions, run as run_descriptions
from test_checkpoints_integration import make_due
from test_visual_gallery_integration import complete
from test_visual_index_integration import queue_index, run as run_index


pytestmark = pytest.mark.integration


def preferences(**changes):
    values = dict(experience="intermediate", difficulty="beginner", language="tr", available_minutes=90,
                  allow_prerequisites=False, allow_extensions=False, allow_external_documentation=False)
    return LearnerPreferences(**(values | changes))


def selection(ingestion, *, key="curriculum-source-key", legacy=False):
    sources, service, principal, project, actor = ingestion
    if legacy:
        source = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(
            filename="legacy.vtt", authorization_mode="owner_upload", idempotency_key=key,
            content="WEBVTT\n\n00:01.000 --> 00:05.000\nLegacy create_app() publishes GET /health.\n",
        )).source
        return SourceSelection(source_id=source.id, generation=1, processing_version=source.processing_version)
    result = register(ingestion, key=key)
    assert run(sources, result)
    source = sources.get_source(principal.tenant_id, project.id, result.source.id)
    return SourceSelection(source_id=source.id, generation=source.active_generation,
                           processing_version=source.processing_version)


def create(ingestion, body):
    sources, _, principal, project, actor = ingestion
    return ContextRepository(sources.store).create(principal.tenant_id, project.id, actor, body)


def saved_counts(ingestion):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return [connection.execute(
            f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
            (principal.tenant_id, project.id),
        ).fetchone()["count"] for table in ("curriculum_contexts", "curriculum_context_sources")]


def wait_for_lock(store, connection_name, future):
    deadline = monotonic() + 5
    while monotonic() < deadline and not future.done():
        with store._connect() as connection:
            blocked = connection.execute(
                "SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock'",
                (connection_name,),
            ).fetchone() is not None
        if blocked:
            return True
        sleep(0.01)
    return False


def test_capture_published_and_legacy_evidence_without_provider_or_artifact_io(ingestion, caplog):
    sources, _, principal, project, actor = ingestion
    selected = [selection(ingestion), selection(ingestion, key="legacy-curriculum-key", legacy=True)]
    sources.artifacts.fail_get = True
    body = ContextCreate(idempotency_key="saved-context-key", selected_sources=selected, learner=preferences())
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        context = create(ingestion, body)
    assert context.tenant_id == principal.tenant_id and context.project_id == project.id
    assert context.request.learner == body.learner
    assert {item.pin.source_id for item in context.tutorial_snapshots} == {item.source_id for item in selected}
    assert sum(len(item.segments) for item in context.tutorial_snapshots) == 2
    assert all(item.segments[0].source_filename for item in context.tutorial_snapshots)
    assert ContextRepository(sources.store).read(principal.tenant_id, project.id, actor, context.id) == context
    body.learner.available_minutes = 1
    assert ContextRepository(sources.store).read(principal.tenant_id, project.id, actor, context.id).request.learner.available_minutes == 90
    events = [record.message for record in caplog.records if "curriculum_context_committed" in record.message]
    assert len(events) == 1 and "create_app" not in events[0] and "source_count" in events[0]
    assert saved_counts(ingestion) == [1, 2]


def test_replay_source_order_normalization_conflict_and_concurrent_create(ingestion, caplog):
    sources, _, principal, project, actor = ingestion
    selected = [selection(ingestion), selection(ingestion, key="second-context-source")]
    body = ContextCreate(idempotency_key="concurrent-context-key", selected_sources=selected, learner=preferences())
    with caplog.at_level("INFO", logger="tutorial_workspace"), ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: create(ingestion, body), range(2)))
    assert values[0] == values[1] and saved_counts(ingestion) == [1, 2]
    replay = body.model_copy(update={"selected_sources": list(reversed(selected))})
    assert create(ingestion, replay) == values[0]
    assert len([record for record in caplog.records if "curriculum_context_committed" in record.message]) == 1
    with pytest.raises(SourceError) as conflict:
        create(ingestion, body.model_copy(update={"learner": preferences(language="en")}))
    assert conflict.value.code == "idempotency_conflict" and conflict.value.status == 409
    repository = ContextRepository(sources.store)
    repository.delete(principal.tenant_id, project.id, actor, values[0].id)
    assert saved_counts(ingestion) == [0, 0]
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, values[0].id)


def test_all_read_write_boundaries_require_both_scopes_and_actor_membership(ingestion):
    sources, service, principal, project, actor = ingestion
    pin = selection(ingestion)
    body = ContextCreate(idempotency_key="isolated-context-key", selected_sources=[pin], learner=preferences())
    context = create(ingestion, body)
    repository = ContextRepository(sources.store)
    other_project = service.create_project(principal, ProjectCreate(title="Other curriculum project"))
    other = AuthenticatedPrincipal(provider="test", subject="other-curriculum-user", tenant_id="foreign-curriculum")
    other_actor = sources.store.bootstrap_principal(other)
    for tenant, scoped_project, scoped_actor in [(other.tenant_id, project.id, other_actor),
                                                 (principal.tenant_id, other_project.id, actor),
                                                 (principal.tenant_id, project.id, other_actor)]:
        for operation in [lambda: repository.read(tenant, scoped_project, scoped_actor, context.id),
                          lambda: repository.delete(tenant, scoped_project, scoped_actor, context.id)]:
            with pytest.raises(ProjectNotFoundError):
                operation()
        with pytest.raises((ProjectNotFoundError, SourceError)):
            repository.create(tenant, scoped_project, scoped_actor, body)
    with sources.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    for operation in [lambda: repository.read(principal.tenant_id, project.id, actor, context.id),
                      lambda: repository.delete(principal.tenant_id, project.id, actor, context.id),
                      lambda: repository.create(principal.tenant_id, project.id, actor, body)]:
        with pytest.raises(ProjectNotFoundError):
            operation()
    assert saved_counts(ingestion) == [1, 1]


def test_archive_preserves_read_replay_delete_but_blocks_new_capture(ingestion):
    sources, service, principal, project, actor = ingestion
    body = ContextCreate(idempotency_key="archived-context-key", selected_sources=[selection(ingestion)], learner=preferences())
    context = create(ingestion, body)
    service.archive_project(principal, project.id)
    repository = ContextRepository(sources.store)
    assert repository.read(principal.tenant_id, project.id, actor, context.id) == context
    assert create(ingestion, body) == context
    with pytest.raises(SourceError) as blocked:
        create(ingestion, body.model_copy(update={"idempotency_key": "new-archived-context-key"}))
    assert blocked.value.code == "project_archived"
    repository.delete(principal.tenant_id, project.id, actor, context.id)
    assert saved_counts(ingestion) == [0, 0]


def test_retained_pin_and_copied_snapshot_survive_reprocessing(ingestion):
    sources, _, principal, project, actor = ingestion
    pin = selection(ingestion)
    body = ContextCreate(idempotency_key="old-generation-context", selected_sources=[pin], learner=preferences())
    context = create(ingestion, body)
    replacement = sources.command(principal.tenant_id, project.id, pin.source_id, actor,
                                  "reprocess", "context-reprocess-key")
    assert run(sources, replacement)
    assert sources.get_source(principal.tenant_id, project.id, pin.source_id).active_generation == 2
    assert ContextRepository(sources.store).read(principal.tenant_id, project.id, actor, context.id) == context
    second = create(ingestion, body.model_copy(update={"idempotency_key": "retain-old-context-again"}))
    assert second.tutorial_snapshots == context.tutorial_snapshots
    assert all(item.pin.generation == 1 for item in second.tutorial_snapshots)


@pytest.mark.parametrize("described", [False, True])
def test_managed_visual_snapshots_preserve_exact_authoritative_provenance(ingestion, description_model, described):
    from app.vision.descriptions import DescriptionRepository
    from app.jobs.visual_indexing import index_visual

    sources, _, principal, project, actor = ingestion
    _, publication = complete(ingestion)
    if described:
        work = queue_descriptions(ingestion, publication)
        assert not run_descriptions(sources, work)
        make_due(sources, work)
        assert run_descriptions(sources, work)
        view = DescriptionRepository(sources).read(principal.tenant_id, project.id, work.source.id, actor)
        assert index_visual(sources, principal.tenant_id, project.id, work.source.id,
                            view.index_job.id, view.index_generation)
    else:
        work = queue_index(ingestion, publication)
        assert run_index(sources, work)
    source = sources.get_source(principal.tenant_id, project.id, work.source.id)
    pin = SourceSelection(source_id=source.id, generation=source.active_generation,
                          processing_version=source.processing_version)
    context = create(ingestion, ContextCreate(idempotency_key="visual-context-key", selected_sources=[pin], learner=preferences()))
    evidence = context.tutorial_snapshots[0].segments
    assert len(evidence) == (4 if described else 2)
    for segment in evidence:
        assert segment == ChatRepository(sources.store).evidence(principal.tenant_id, project.id, actor, segment.segment_id)
        assert segment.visual_origin is not None and segment.frame_id is not None and segment.asr_origin is None
        assert (segment.visual_origin.description is not None) == described
    # An inconsistent managed projection must never be downgraded to legacy data.
    with sources.store._connect() as connection:
        connection.execute("UPDATE content_segments SET visual_publication_job_id=NULL WHERE tenant_id=%s AND project_id=%s AND source_id=%s",
                           (principal.tenant_id, project.id, pin.source_id))
    with pytest.raises(SourceError) as broken:
        create(ingestion, ContextCreate(idempotency_key="broken-visual-context", selected_sources=[pin], learner=preferences()))
    assert broken.value.code == "invalid_visual_provenance" and saved_counts(ingestion) == [1, 1]


@pytest.mark.parametrize("invalid", ["future", "parser", "unknown", "empty", "version_row", "mixed_parser"])
def test_invalid_pins_never_save_partial_context(ingestion, invalid):
    sources, _, principal, project, _ = ingestion
    pin = selection(ingestion)
    if invalid == "future":
        pin = pin.model_copy(update={"generation": 2})
    elif invalid == "parser":
        pin = pin.model_copy(update={"processing_version": "foreign-parser-v1"})
    elif invalid == "unknown":
        pin = pin.model_copy(update={"source_id": uuid4()})
    else:
        with sources.store._connect() as connection:
            scope = (principal.tenant_id, project.id, pin.source_id)
            if invalid == "empty":
                connection.execute("DELETE FROM content_segments WHERE tenant_id=%s AND project_id=%s AND source_id=%s", scope)
            elif invalid == "version_row":
                connection.execute("UPDATE processing_versions SET processing_version='mismatch' WHERE tenant_id=%s AND project_id=%s AND source_id=%s", scope)
            elif invalid == "mixed_parser":
                connection.execute("UPDATE content_segments SET processing_version='mismatch' WHERE tenant_id=%s AND project_id=%s AND source_id=%s", scope)
    with pytest.raises(SourceError) as unavailable:
        create(ingestion, ContextCreate(idempotency_key="invalid-context-key", selected_sources=[pin], learner=preferences()))
    assert unavailable.value.code == "curriculum_source_unavailable" and saved_counts(ingestion) == [0, 0]


def test_pending_source_is_not_published_context(ingestion):
    pending = register(ingestion)
    pin = SourceSelection(source_id=pending.source.id, generation=1, processing_version="transcript-chunks-v1:g1")
    with pytest.raises(SourceError) as unavailable:
        create(ingestion, ContextCreate(idempotency_key="pending-context-key", selected_sources=[pin], learner=preferences()))
    assert unavailable.value.code == "curriculum_source_unavailable" and saved_counts(ingestion) == [0, 0]


@pytest.mark.parametrize("limit", ["segments", "characters", "segment_text"])
def test_aggregate_and_per_segment_limits_reject_without_truncation(ingestion, limit):
    sources, _, principal, project, _ = ingestion
    pin = selection(ingestion)
    with sources.store._connect() as connection:
        if limit == "segment_text":
            connection.execute("UPDATE content_segments SET text=repeat('x',10001) WHERE tenant_id=%s AND project_id=%s AND source_id=%s",
                               (principal.tenant_id, project.id, pin.source_id))
        else:
            count = 500 if limit == "segments" else 50
            width = 1 if limit == "segments" else 10000
            connection.execute("""INSERT INTO content_segments
                (id,tenant_id,project_id,source_id,modality,start_ms,end_ms,text,embedding,processing_version,generation)
                SELECT gen_random_uuid(),tenant_id,project_id,source_id,modality,10000+i*2,10001+i*2,
                       repeat('x',%s),embedding,processing_version,generation
                FROM content_segments CROSS JOIN generate_series(1,%s) AS i
                WHERE tenant_id=%s AND project_id=%s AND source_id=%s""",
                (width, count, principal.tenant_id, project.id, pin.source_id))
    with pytest.raises(SourceError) as overflow:
        create(ingestion, ContextCreate(idempotency_key="overflow-context-key", selected_sources=[pin], learner=preferences()))
    expected = "curriculum_source_unavailable" if limit == "segment_text" else "curriculum_evidence_too_large"
    assert overflow.value.code == expected and saved_counts(ingestion) == [0, 0]


def test_source_delete_removes_complete_multi_source_copy_and_project_cascades(ingestion):
    sources, service, principal, project, actor = ingestion
    pins = [selection(ingestion), selection(ingestion, key="second-deletion-source")]
    context = create(ingestion, ContextCreate(idempotency_key="multi-source-context", selected_sources=pins, learner=preferences()))
    with sources.store._connect() as connection:
        # The DB trigger protects even callers that delete directly.
        connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, pins[0].source_id))
    assert saved_counts(ingestion) == [0, 0]
    with pytest.raises(ProjectNotFoundError):
        ContextRepository(sources.store).read(principal.tenant_id, project.id, actor, context.id)
    create(ingestion, ContextCreate(idempotency_key="project-cascade-context", selected_sources=[pins[1]], learner=preferences()))
    service.delete_project(principal, project.id)
    assert saved_counts(ingestion) == [0, 0]


@pytest.mark.parametrize("direct", [False, True])
def test_context_capture_holds_fence_until_complete_source_delete(ingestion, monkeypatch, direct):
    sources, _, principal, project, actor = ingestion
    pin = selection(ingestion)
    repository = ContextRepository(sources.store)
    captured, release, deletion_started = Event(), Event(), Event()
    original = repository._snapshots

    def pause(connection, request):
        snapshots = original(connection, request)
        captured.set()
        assert release.wait(10)
        return snapshots

    monkeypatch.setattr(repository, "_snapshots", pause)
    body = ContextCreate(idempotency_key="fenced-context-key", selected_sources=[pin], learner=preferences())
    connection_name = "curriculum-delete-fence-" + uuid4().hex

    def delete_source():
        if direct:
            with sources.store._connect() as connection:
                connection.execute("SELECT set_config('application_name',%s,false)", (connection_name,))
                deletion_started.set()
                connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (principal.tenant_id, project.id, pin.source_id))
            return
        deletion_started.set()
        return sources.delete_source(principal.tenant_id, project.id, pin.source_id, actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.create, principal.tenant_id, project.id, actor, body)
        try:
            assert captured.wait(10)
            deletion = pool.submit(delete_source)
            assert deletion_started.wait(10)
            if direct:
                assert wait_for_lock(sources.store, connection_name, deletion), "Direct deletion must wait for the source fence"
            assert not deletion.done()
        finally:
            release.set()
        context = pending.result(timeout=10)
        deletion.result(timeout=10)
    assert saved_counts(ingestion) == [0, 0]
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, context.id)


def test_membership_revocation_waits_for_capture_then_denies_repository_access(ingestion, monkeypatch):
    sources, _, principal, project, actor = ingestion
    pin = selection(ingestion)
    repository = ContextRepository(sources.store)
    captured, release, revocation_started = Event(), Event(), Event()
    original = repository._snapshots
    connection_name = "curriculum-membership-fence-" + uuid4().hex

    def pause(connection, request):
        snapshots = original(connection, request)
        captured.set()
        assert release.wait(10)
        return snapshots

    def revoke():
        with sources.store._connect() as connection:
            connection.execute("SELECT set_config('application_name',%s,false)", (connection_name,))
            revocation_started.set()
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))

    monkeypatch.setattr(repository, "_snapshots", pause)
    body = ContextCreate(idempotency_key="membership-fenced-context", selected_sources=[pin], learner=preferences())
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.create, principal.tenant_id, project.id, actor, body)
        try:
            assert captured.wait(10)
            revocation = pool.submit(revoke)
            assert revocation_started.wait(10)
            assert wait_for_lock(sources.store, connection_name, revocation)
        finally:
            release.set()
        context = pending.result(timeout=10)
        revocation.result(timeout=10)
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, context.id)
    with pytest.raises(ProjectNotFoundError):
        repository.create(principal.tenant_id, project.id, actor,
                          body.model_copy(update={"idempotency_key": "after-membership-revoked"}))
    assert saved_counts(ingestion) == [1, 1]


def test_serialized_snapshot_byte_cap_has_no_partial_saved_record(ingestion, monkeypatch):
    pin = selection(ingestion)
    monkeypatch.setattr("app.curriculum.repository.MAX_CONTEXT_BYTES", 10)
    with pytest.raises(SourceError) as overflow:
        create(ingestion, ContextCreate(idempotency_key="context-byte-cap-key", selected_sources=[pin], learner=preferences()))
    assert overflow.value.code == "curriculum_evidence_too_large" and saved_counts(ingestion) == [0, 0]


def test_constructed_or_mutated_input_does_not_bypass_validation(ingestion):
    pin = selection(ingestion)
    invalid_bodies = [
        ContextCreate.model_construct(idempotency_key="invalid", selected_sources=[], learner=preferences()),
        ContextCreate.model_construct(idempotency_key="constructed-context", selected_sources=[pin], learner=preferences().model_copy(update={"allow_extensions": "false"})),
        ContextCreate(idempotency_key="mutated-context-key", selected_sources=[pin], learner=preferences()).model_copy(update={"selected_sources": [pin, pin]}),
    ]
    for body in invalid_bodies:
        with pytest.raises(SourceError) as rejected:
            create(ingestion, body)
        assert rejected.value.code == "invalid_curriculum_context"
    assert saved_counts(ingestion) == [0, 0]
