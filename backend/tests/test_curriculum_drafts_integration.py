"""Synthetic PostgreSQL draft history, authorization and deletion fences."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from app.curriculum.contracts import AssignmentContent
from app.curriculum.drafts import DraftRepository
from app.curriculum.persistence import ContextCreate, DraftCreate, DraftReplace
from app.curriculum.repository import ContextRepository
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_curriculum_contexts_integration import preferences, selection, wait_for_lock
from test_ingestion_integration import ingestion, run
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def saved_context(ingestion, *, key="draft-context-key", multiple=False, **learner):
    sources, _, principal, project, actor = ingestion
    pins = [selection(ingestion, key=key + "-source")]
    if multiple:
        pins.append(selection(ingestion, key=key + "-other-source"))
    return ContextRepository(sources.store).create(
        principal.tenant_id, project.id, actor,
        ContextCreate(idempotency_key=key, selected_sources=pins, learner=preferences(**learner)),
    )


def content_for(context, *, title="A synthetic health API"):
    segment = context.tutorial_snapshots[0].segments[0].segment_id
    return AssignmentContent(
        schema_version="assignment-draft-v1", title=title,
        scenario="Provide a health endpoint using synthetic application data.", estimated_minutes=60,
        objectives=[{"id": "routes", "description": "Define an API route.",
                     "tutorial_segment_ids": [segment]}],
        requirements=[{"id": "health", "label": "covered", "description": "Expose GET /health.",
                       "objective_ids": ["routes"], "tutorial_segment_ids": [segment],
                       "documentation_excerpt_ids": []}],
        constraints=["Use synthetic data."], deliverables=["Python source files."],
        acceptance_criteria=[{"id": "healthy", "description": "GET /health returns a successful response.",
                              "requirement_ids": ["health"]}],
        rubric=[{"id": "clarity", "description": "Describe the API clearly.",
                 "acceptance_criterion_ids": ["healthy"]}],
        hints=[{"id": "route-hint", "level": 1, "text": "Review the route decorator.",
                "requirement_ids": ["health"]}],
    )


def create_draft(ingestion, context, *, key="create-draft-key", content=None):
    sources, _, principal, project, actor = ingestion
    body = DraftCreate(idempotency_key=key, content=content or content_for(context))
    return DraftRepository(sources.store).create(principal.tenant_id, project.id, actor, context.id, body)


def counts(ingestion):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return [connection.execute(
            f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s",
            (principal.tenant_id, project.id),
        ).fetchone()["count"] for table in
            ("curriculum_drafts", "curriculum_draft_revisions", "curriculum_draft_commands")]


def test_save_bound_content_read_detached_history_and_safe_log(ingestion, caplog):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    content = content_for(context)
    sources.artifacts.fail_get = True
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        saved = create_draft(ingestion, context, content=content)
    repository = DraftRepository(sources.store)
    assert saved.revision == 1 and saved.context_id == context.id
    assert saved.assignment.draft.tenant_id == principal.tenant_id
    assert saved.assignment.draft.project_id == project.id
    assert saved.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    assert saved.assignment.documentation_snapshots == []
    assert repository.read(principal.tenant_id, project.id, actor, saved.id) == saved
    assert repository.read(principal.tenant_id, project.id, actor, saved.id, 1) == saved
    content.title = "Changed caller input"
    saved.assignment.draft.title = "Changed response instance"
    restored = repository.read(principal.tenant_id, project.id, actor, saved.id)
    assert restored.assignment.draft.title == "A synthetic health API"
    assert counts(ingestion) == [1, 1, 1]
    events = [record.message for record in caplog.records if "curriculum_draft_created" in record.message]
    assert len(events) == 1 and "objective_count" in events[0]
    assert "synthetic health" not in events[0] and "create_app" not in events[0]


def test_durable_receipts_replay_exact_earlier_success_after_later_edits(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    edit = DraftReplace(idempotency_key="first-edit-key", expected_revision=1,
                        content=content_for(context, title="Second revision"))
    second = repository.replace(principal.tenant_id, project.id, actor, first.id, edit)
    third = repository.replace(principal.tenant_id, project.id, actor, first.id, DraftReplace(
        idempotency_key="second-edit-key", expected_revision=2, content=content_for(context, title="Third revision")))
    assert (first.revision, second.revision, third.revision) == (1, 2, 3)
    assert create_draft(ingestion, context) == first
    assert repository.replace(principal.tenant_id, project.id, actor, first.id, edit) == second
    assert repository.read(principal.tenant_id, project.id, actor, first.id) == third
    assert repository.read(principal.tenant_id, project.id, actor, first.id, 1) == first
    assert repository.read(principal.tenant_id, project.id, actor, first.id, 2) == second
    assert counts(ingestion) == [1, 3, 3]


@pytest.mark.parametrize("changed", ["content", "context", "operation", "expected_revision", "draft"])
def test_project_command_key_cannot_mean_different_input(ingestion, changed):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    edit = DraftReplace(idempotency_key="existing-edit-key", expected_revision=1,
                        content=content_for(context, title="Second revision"))
    repository.replace(principal.tenant_id, project.id, actor, first.id, edit)
    with pytest.raises(SourceError) as conflict:
        if changed == "content":
            create_draft(ingestion, context, content=content_for(context, title="Different content"))
        elif changed == "context":
            other = saved_context(ingestion, key="other-draft-context")
            create_draft(ingestion, other, content=content_for(context))
        elif changed == "operation":
            repository.replace(principal.tenant_id, project.id, actor, first.id,
                               edit.model_copy(update={"idempotency_key": "create-draft-key"}))
        elif changed == "expected_revision":
            repository.replace(principal.tenant_id, project.id, actor, first.id,
                               edit.model_copy(update={"expected_revision": 2}))
        else:
            repository.replace(principal.tenant_id, project.id, actor, uuid4(), edit)
    assert conflict.value.code == "idempotency_conflict" and conflict.value.status == 409
    assert counts(ingestion) == [1, 2, 2]


def test_concurrent_create_and_edit_retry_each_commit_once(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = list(pool.map(lambda _: create_draft(ingestion, context), range(2)))
    assert first[0] == first[1] and counts(ingestion) == [1, 1, 1]
    repository = DraftRepository(sources.store)
    body = DraftReplace(idempotency_key="concurrent-edit-key", expected_revision=1,
                        content=content_for(context, title="Concurrent accepted edit"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        second = list(pool.map(lambda _: repository.replace(principal.tenant_id, project.id, actor, first[0].id, body), range(2)))
    assert second[0] == second[1] and second[0].revision == 2
    assert counts(ingestion) == [1, 2, 2]


def test_competing_edits_require_latest_revision_and_noop_is_new_version(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)

    def edit(index):
        body = DraftReplace(idempotency_key=f"competing-edit-{index}", expected_revision=1,
                            content=content_for(context, title=f"Competing edit {index}"))
        try:
            return repository.replace(principal.tenant_id, project.id, actor, first.id, body)
        except SourceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, range(2)))
    errors = [result for result in results if isinstance(result, SourceError)]
    assert len(errors) == 1 and errors[0].code == "draft_revision_conflict"
    second = repository.read(principal.tenant_id, project.id, actor, first.id)
    same_content = AssignmentContent.model_validate_json(second.assignment.draft.model_dump_json(
        exclude={"tenant_id", "project_id"}))
    third = repository.replace(principal.tenant_id, project.id, actor, first.id, DraftReplace(
        idempotency_key="explicit-noop-edit", expected_revision=2, content=same_content))
    assert third.revision == 3 and third.assignment == second.assignment
    assert counts(ingestion) == [1, 3, 3]


def test_every_operation_checks_both_scopes_and_membership(ingestion):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    other_project = service.create_project(principal, ProjectCreate(title="Other draft project"))
    other = AuthenticatedPrincipal(provider="test", subject="other-draft-user", tenant_id="foreign-draft")
    other_actor = sources.store.bootstrap_principal(other)
    create = DraftCreate(idempotency_key="scoped-create-key", content=content_for(context))
    edit = DraftReplace(idempotency_key="scoped-edit-key", expected_revision=1, content=content_for(context))
    for tenant, scoped_project, scoped_actor in [(other.tenant_id, project.id, other_actor),
                                                 (principal.tenant_id, other_project.id, actor),
                                                 (principal.tenant_id, project.id, other_actor)]:
        for operation in [lambda: repository.create(tenant, scoped_project, scoped_actor, context.id, create),
                          lambda: repository.replace(tenant, scoped_project, scoped_actor, first.id, edit),
                          lambda: repository.read(tenant, scoped_project, scoped_actor, first.id),
                          lambda: repository.read(tenant, scoped_project, scoped_actor, first.id, 1),
                          lambda: repository.delete(tenant, scoped_project, scoped_actor, first.id)]:
            with pytest.raises(ProjectNotFoundError):
                operation()
    with sources.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    for operation in [lambda: repository.create(principal.tenant_id, project.id, actor, context.id, create),
                      lambda: repository.replace(principal.tenant_id, project.id, actor, first.id, edit),
                      lambda: repository.read(principal.tenant_id, project.id, actor, first.id),
                      lambda: repository.delete(principal.tenant_id, project.id, actor, first.id)]:
        with pytest.raises(ProjectNotFoundError):
            operation()
    assert counts(ingestion) == [1, 1, 1]


def test_archive_allows_history_and_accepted_replays_but_blocks_new_mutations(ingestion):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    edit = DraftReplace(idempotency_key="pre-archive-edit", expected_revision=1,
                        content=content_for(context, title="Accepted before archive"))
    second = repository.replace(principal.tenant_id, project.id, actor, first.id, edit)
    service.archive_project(principal, project.id)
    assert repository.read(principal.tenant_id, project.id, actor, first.id) == second
    assert repository.read(principal.tenant_id, project.id, actor, first.id, 1) == first
    assert create_draft(ingestion, context) == first
    assert repository.replace(principal.tenant_id, project.id, actor, first.id, edit) == second
    for operation in [lambda: create_draft(ingestion, context, key="new-archived-draft"),
                      lambda: repository.replace(principal.tenant_id, project.id, actor, first.id,
                          edit.model_copy(update={"idempotency_key": "new-archived-edit", "expected_revision": 2}))]:
        with pytest.raises(SourceError) as blocked:
            operation()
        assert blocked.value.code == "project_archived"
    repository.delete(principal.tenant_id, project.id, actor, first.id)
    assert counts(ingestion) == [0, 0, 0]


@pytest.mark.parametrize("invalid", ["evidence", "effort", "external", "nul", "constructed", "mutated"])
def test_invalid_new_content_cannot_save_partial_draft_or_receipt(ingestion, invalid):
    context = saved_context(ingestion, allow_extensions=True, allow_external_documentation=True)
    content = content_for(context)
    if invalid == "evidence":
        content.objectives[0].tutorial_segment_ids = [uuid4()]
    elif invalid == "effort":
        content.estimated_minutes = 91
    elif invalid == "external":
        content.requirements[0].label = "extension"
        content.requirements[0].documentation_excerpt_ids = [uuid4()]
    elif invalid == "nul":
        content.scenario = "A JSON-valid but PostgreSQL-incompatible \x00 text."
    elif invalid == "constructed":
        content = AssignmentContent.model_construct(**(content.model_dump() | {"requirements": []}))
    else:
        content.requirements[0].objective_ids = ["missing-objective"]
    body = DraftCreate.model_construct(idempotency_key="invalid-new-draft", content=content)
    sources, _, principal, project, actor = ingestion
    with pytest.raises(SourceError) as rejected:
        DraftRepository(sources.store).create(principal.tenant_id, project.id, actor, context.id, body)
    assert rejected.value.code == "invalid_curriculum_draft" and rejected.value.status == 422
    assert counts(ingestion) == [0, 0, 0]


def test_failed_edit_preserves_head_history_and_does_not_reserve_key(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    content = content_for(context)
    content.objectives[0].tutorial_segment_ids = [uuid4()]
    body = DraftReplace(idempotency_key="invalid-then-fixed-edit", expected_revision=1, content=content)
    with pytest.raises(SourceError) as rejected:
        repository.replace(principal.tenant_id, project.id, actor, first.id, body)
    assert rejected.value.code == "invalid_curriculum_draft"
    assert repository.read(principal.tenant_id, project.id, actor, first.id) == first
    assert counts(ingestion) == [1, 1, 1]
    fixed = body.model_copy(update={"content": content_for(context)})
    second = repository.replace(principal.tenant_id, project.id, actor, first.id, fixed)
    assert second.revision == 2 and counts(ingestion) == [1, 2, 2]


def test_storage_byte_cap_and_transaction_failure_leave_no_partial_rows(ingestion, monkeypatch):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = DraftRepository(sources.store)
    body = DraftCreate(idempotency_key="atomic-draft-create", content=content_for(context))
    with monkeypatch.context() as patch:
        patch.setattr("app.curriculum.drafts.MAX_DRAFT_STORAGE_BYTES", 10)
        with pytest.raises(SourceError) as rejected:
            repository.create(principal.tenant_id, project.id, actor, context.id, body)
        assert rejected.value.code == "invalid_curriculum_draft"
    assert counts(ingestion) == [0, 0, 0]
    append = repository._append

    def fail_after_insert(*args, **kwargs):
        append(*args, **kwargs)
        raise SourceError("synthetic_transaction_failure", "Synthetic transaction failure.", 503)

    with monkeypatch.context() as patch:
        patch.setattr(repository, "_append", fail_after_insert)
        with pytest.raises(SourceError) as rejected:
            repository.create(principal.tenant_id, project.id, actor, context.id, body)
        assert rejected.value.code == "synthetic_transaction_failure"
    assert counts(ingestion) == [0, 0, 0]
    assert repository.create(principal.tenant_id, project.id, actor, context.id, body).revision == 1


def test_literal_unicode_escape_is_content_and_retained_evidence_survives_reprocess(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    content = content_for(context)
    content.scenario = r"Treat the literal text \u0000 as six characters."
    first = create_draft(ingestion, context, content=content)
    source_id = context.request.selected_sources[0].source_id
    replacement = sources.command(principal.tenant_id, project.id, source_id, actor, "reprocess", "draft-reprocess-key")
    assert run(sources, replacement)
    assert sources.get_source(principal.tenant_id, project.id, source_id).active_generation == 2
    repository = DraftRepository(sources.store)
    second = repository.replace(principal.tenant_id, project.id, actor, first.id, DraftReplace(
        idempotency_key="old-context-edit", expected_revision=1, content=content_for(context, title="Retained context edit")))
    assert second.assignment.tutorial_evidence == first.assignment.tutorial_evidence
    assert all(item.generation == 1 for item in second.assignment.tutorial_evidence)
    assert repository.read(principal.tenant_id, project.id, actor, first.id, 1) == first


@pytest.mark.parametrize("target", ["draft", "context", "source", "direct_source", "project"])
def test_complete_delete_cascades_revision_text_and_receipts(ingestion, target):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion, multiple=True)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    body = DraftReplace(idempotency_key="deleted-draft-edit", expected_revision=1,
                        content=content_for(context, title="Deleted revision text"))
    repository.replace(principal.tenant_id, project.id, actor, first.id, body)
    if target == "draft":
        repository.delete(principal.tenant_id, project.id, actor, first.id)
    elif target == "context":
        ContextRepository(sources.store).delete(principal.tenant_id, project.id, actor, context.id)
    elif target == "source":
        sources.delete_source(principal.tenant_id, project.id, context.request.selected_sources[1].source_id, actor)
    elif target == "direct_source":
        with sources.store._connect() as connection:
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (principal.tenant_id, project.id, context.request.selected_sources[1].source_id))
    else:
        service.delete_project(principal, project.id)
    assert counts(ingestion) == [0, 0, 0]
    for operation in [lambda: repository.read(principal.tenant_id, project.id, actor, first.id),
                      lambda: repository.read(principal.tenant_id, project.id, actor, first.id, 1),
                      lambda: repository.replace(principal.tenant_id, project.id, actor, first.id, body),
                      lambda: repository.delete(principal.tenant_id, project.id, actor, first.id)]:
        with pytest.raises(ProjectNotFoundError):
            operation()
    if target != "draft":
        with pytest.raises(ProjectNotFoundError):
            create_draft(ingestion, context)


@pytest.mark.parametrize("target", ["source", "context"])
def test_capture_fence_waits_for_direct_dependency_delete_without_lock_inversion(ingestion, monkeypatch, target):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = DraftRepository(sources.store)
    captured, release, deletion_started = Event(), Event(), Event()
    original = repository._bind
    connection_name = "draft-delete-fence-" + uuid4().hex

    def pause(tenant, scoped_project, saved, content, documentation_snapshots=None):
        result = original(tenant, scoped_project, saved, content, documentation_snapshots)
        captured.set()
        assert release.wait(10)
        return result

    def remove_dependency():
        with sources.store._connect() as connection:
            connection.execute("SELECT set_config('application_name',%s,false)", (connection_name,))
            deletion_started.set()
            if target == "source":
                connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (principal.tenant_id, project.id, context.request.selected_sources[0].source_id))
            else:
                connection.execute("DELETE FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (principal.tenant_id, project.id, context.id))

    monkeypatch.setattr(repository, "_bind", pause)
    body = DraftCreate(idempotency_key="fenced-draft-create", content=content_for(context))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.create, principal.tenant_id, project.id, actor, context.id, body)
        try:
            assert captured.wait(10)
            deletion = pool.submit(remove_dependency)
            assert deletion_started.wait(10)
            assert wait_for_lock(sources.store, connection_name, deletion), "Deletion must wait for the context fence"
        finally:
            release.set()
        accepted = pending.result(timeout=10)
        deletion.result(timeout=10)
    assert counts(ingestion) == [0, 0, 0]
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, accepted.id)


def test_membership_revocation_waits_for_commit_then_denies_repository_replay(ingestion, monkeypatch):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repository = DraftRepository(sources.store)
    captured, release, revocation_started = Event(), Event(), Event()
    original = repository._bind
    connection_name = "draft-membership-fence-" + uuid4().hex

    def pause(tenant, scoped_project, saved, content, documentation_snapshots=None):
        result = original(tenant, scoped_project, saved, content, documentation_snapshots)
        captured.set()
        assert release.wait(10)
        return result

    def revoke():
        with sources.store._connect() as connection:
            connection.execute("SELECT set_config('application_name',%s,false)", (connection_name,))
            revocation_started.set()
            connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))

    monkeypatch.setattr(repository, "_bind", pause)
    body = DraftCreate(idempotency_key="membership-fenced-draft", content=content_for(context))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.create, principal.tenant_id, project.id, actor, context.id, body)
        try:
            assert captured.wait(10)
            revocation = pool.submit(revoke)
            assert revocation_started.wait(10)
            assert wait_for_lock(sources.store, connection_name, revocation)
        finally:
            release.set()
        saved = pending.result(timeout=10)
        revocation.result(timeout=10)
    with pytest.raises(ProjectNotFoundError):
        repository.create(principal.tenant_id, project.id, actor, context.id, body)
    with pytest.raises(ProjectNotFoundError):
        repository.read(principal.tenant_id, project.id, actor, saved.id)
    assert counts(ingestion) == [1, 1, 1]


def test_missing_draft_context_and_revision_return_not_found(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    first = create_draft(ingestion, context)
    repository = DraftRepository(sources.store)
    body = DraftCreate(idempotency_key="missing-context-create", content=content_for(context))
    with pytest.raises(ProjectNotFoundError):
        repository.create(principal.tenant_id, project.id, actor, uuid4(), body)
    for operation in [lambda: repository.read(principal.tenant_id, project.id, actor, uuid4()),
                      lambda: repository.read(principal.tenant_id, project.id, actor, first.id, 2),
                      lambda: repository.delete(principal.tenant_id, project.id, actor, uuid4())]:
        with pytest.raises(ProjectNotFoundError):
            operation()
    for revision in [0, -1, True, "1", 2_147_483_648]:
        with pytest.raises(SourceError) as invalid:
            repository.read(principal.tenant_id, project.id, actor, first.id, revision)
        assert invalid.value.code == "invalid_curriculum_draft"
    assert counts(ingestion) == [1, 1, 1]
