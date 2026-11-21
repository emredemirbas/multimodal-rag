"""Reviewed activation pins immutable synthetic evidence without model or file IO."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, current_thread
from uuid import uuid4

from psycopg.types.json import Jsonb
import pytest

from app.curriculum.assignments import AssignmentRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.persistence import AssignmentActivate, DraftReplace
from app.curriculum.repository import ContextRepository
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_curriculum_contexts_integration import wait_for_lock
from test_curriculum_draft_documents_integration import draft_request, setup as document_setup
from test_curriculum_drafts_integration import content_for, counts, create_draft, saved_context
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration


def activation_body(key="reviewed-activation-key", revision=1):
    return AssignmentActivate(idempotency_key=key, expected_revision=revision,
                              consent="activate_reviewed_revision")


def activation_setup(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    draft = create_draft(ingestion, context)
    return AssignmentRepository(sources.store), (principal.tenant_id, project.id, actor), context, draft


def version_count(ingestion):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return connection.execute(
            "SELECT count(*) AS n FROM curriculum_assignment_versions WHERE tenant_id=%s AND project_id=%s",
            (principal.tenant_id, project.id),
        ).fetchone()["n"]


def test_activation_requires_explicit_action_and_pins_detached_exact_revision(ingestion, caplog):
    repository, scope, context, draft = activation_setup(ingestion)
    assert repository.latest(*scope, draft.id) is None
    assert version_count(ingestion) == 0 and counts(ingestion) == [1, 1, 1]
    ingestion[0].artifacts.fail_get = ingestion[0].artifacts.fail_put = True
    body = activation_body()
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        activated = repository.activate(*scope, draft.id, body)
    assert activated.id != draft.id
    assert (activated.tenant_id, activated.project_id, activated.activated_by) == scope
    assert activated.context_id == context.id and activated.draft_id == draft.id
    assert activated.revision == 1 and activated.draft == draft
    assert activated.activated_at.tzinfo is not None
    assert repository.read(*scope, activated.id) == activated
    assert repository.latest(*scope, draft.id) == activated
    assert repository.activate(*scope, draft.id, body) == activated
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 1, 2]
    activated.draft.assignment.draft.title = "Mutated response must not rewrite storage"
    assert repository.read(*scope, activated.id).draft == draft
    messages = " ".join(record.message for record in caplog.records)
    assert "A synthetic health API" not in messages
    assert "reviewed-activation-key" not in messages and "create_app" not in messages


def test_later_edits_and_activation_preserve_original_version_and_exact_replay(ingestion):
    repository, scope, context, first = activation_setup(ingestion)
    body = activation_body()
    activated = repository.activate(*scope, first.id, body)
    second = DraftRepository(ingestion[0].store).replace(*scope, first.id, DraftReplace(
        idempotency_key="edited-after-activation", expected_revision=1,
        content=content_for(context, title="Independently reviewed second revision")))
    assert second.revision == 2
    assert repository.read(*scope, activated.id) == activated
    assert repository.latest(*scope, first.id) == activated
    assert repository.activate(*scope, first.id, body) == activated
    with pytest.raises(SourceError) as stale:
        repository.activate(*scope, first.id, activation_body("stale-new-activation", 1))
    assert stale.value.code == "draft_revision_conflict"
    newer = repository.activate(*scope, first.id, activation_body("new-reviewed-activation", 2))
    assert newer.id != activated.id and newer.revision == 2 and newer.draft == second
    assert repository.latest(*scope, first.id) == newer
    assert repository.read(*scope, activated.id) == activated
    assert version_count(ingestion) == 2 and counts(ingestion) == [1, 2, 4]


def test_new_key_for_current_activated_revision_preserves_original_actor_and_timestamp(ingestion):
    repository, scope, _, draft = activation_setup(ingestion)
    first = repository.activate(*scope, draft.id, activation_body())
    principal = AuthenticatedPrincipal(provider="test", subject="second-reviewer", tenant_id=scope[0])
    second_actor = ingestion[0].store.bootstrap_principal(principal)
    alternate = (*scope[:2], second_actor)
    second = repository.activate(*alternate, draft.id, activation_body("second-reviewed-activation"))
    assert second == first and second.activated_by == scope[2]
    assert repository.activate(*alternate, draft.id, activation_body("second-reviewed-activation")) == first
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 1, 3]


def test_activation_keys_share_namespace_with_draft_create_replace_and_target(ingestion):
    repository, scope, context, draft = activation_setup(ingestion)
    with pytest.raises(SourceError) as create_collision:
        repository.activate(*scope, draft.id, activation_body("create-draft-key"))
    assert create_collision.value.code == "idempotency_conflict"
    body = activation_body()
    original = repository.activate(*scope, draft.id, body)
    other = create_draft(ingestion, context, key="another-activation-target")
    for target, request in [(other.id, body), (draft.id, activation_body(revision=2))]:
        with pytest.raises(SourceError) as conflict:
            repository.activate(*scope, target, request)
        assert conflict.value.code == "idempotency_conflict"
    with pytest.raises(SourceError) as replace_collision:
        DraftRepository(ingestion[0].store).replace(*scope, draft.id, DraftReplace(
            idempotency_key=body.idempotency_key, expected_revision=1, content=content_for(context)))
    assert replace_collision.value.code == "idempotency_conflict"
    assert repository.read(*scope, original.id) == original
    assert version_count(ingestion) == 1 and counts(ingestion) == [2, 2, 3]


def test_archive_preserves_read_and_same_key_replay_but_blocks_new_activation_receipts(ingestion):
    repository, scope, context, draft = activation_setup(ingestion)
    body = activation_body()
    activated = repository.activate(*scope, draft.id, body)
    DraftRepository(ingestion[0].store).replace(*scope, draft.id, DraftReplace(
        idempotency_key="pre-archive-revision-two", expected_revision=1, content=content_for(context)))
    ingestion[1].archive_project(ingestion[2], ingestion[3].id)
    assert repository.read(*scope, activated.id) == activated
    assert repository.latest(*scope, draft.id) == activated
    assert repository.activate(*scope, draft.id, body) == activated
    for revision in [1, 2]:
        with pytest.raises(SourceError) as archived:
            repository.activate(*scope, draft.id, activation_body(f"new-archived-activation-{revision}", revision))
        assert archived.value.code == "project_archived"
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 2, 3]


def test_repository_activation_read_and_latest_enforce_scope_and_membership(ingestion):
    repository, scope, _, draft = activation_setup(ingestion)
    activated = repository.activate(*scope, draft.id, activation_body())
    foreign = AuthenticatedPrincipal(provider="test", subject="foreign-activation-user", tenant_id="foreign-activation")
    foreign_actor = ingestion[0].store.bootstrap_principal(foreign)
    other = ingestion[1].create_project(ingestion[2], ProjectCreate(title="Unrelated activation project"))
    invalid_scopes = [(foreign.tenant_id, scope[1], foreign_actor),
                      (scope[0], other.id, scope[2]), (scope[0], scope[1], foreign_actor)]
    with ingestion[0].store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (scope[0], scope[2]))
    invalid_scopes.append(scope)
    for invalid in invalid_scopes:
        for operation in [lambda: repository.activate(*invalid, draft.id, activation_body()),
                          lambda: repository.read(*invalid, activated.id),
                          lambda: repository.latest(*invalid, draft.id)]:
            with pytest.raises(ProjectNotFoundError):
                operation()
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 1, 2]


@pytest.mark.parametrize("value", [True, "1", 0, -1, 2_147_483_648])
def test_repository_revalidates_constructed_activation_input_without_partial_receipt(ingestion, value):
    repository, scope, _, draft = activation_setup(ingestion)
    request = AssignmentActivate.model_construct(idempotency_key="constructed-activation", expected_revision=value,
                                                consent="activate_reviewed_revision")
    with pytest.raises(SourceError) as invalid:
        repository.activate(*scope, draft.id, request)
    assert invalid.value.code == "invalid_assignment_activation" and invalid.value.status == 422
    assert version_count(ingestion) == 0 and counts(ingestion) == [1, 1, 1]
    assert repository.activate(*scope, draft.id, activation_body("constructed-activation")).revision == 1


def test_corrupt_stored_evidence_cannot_be_activated_or_consume_retry_key(ingestion):
    repository, scope, _, draft = activation_setup(ingestion)
    with ingestion[0].store._connect() as connection:
        row = connection.execute("SELECT content FROM curriculum_draft_revisions WHERE tenant_id=%s AND project_id=%s AND draft_id=%s",
                                 (*scope[:2], draft.id)).fetchone()
        original = row["content"]
        corrupted = deepcopy(original)
        corrupted["objectives"][0]["tutorial_segment_ids"] = [str(uuid4())]
        connection.execute("UPDATE curriculum_draft_revisions SET content=%s WHERE tenant_id=%s AND project_id=%s AND draft_id=%s",
                           (Jsonb(corrupted), *scope[:2], draft.id))
    with pytest.raises(SourceError) as invalid:
        repository.activate(*scope, draft.id, activation_body())
    assert invalid.value.code == "invalid_curriculum_draft"
    assert version_count(ingestion) == 0 and counts(ingestion) == [1, 1, 1]
    with ingestion[0].store._connect() as connection:
        connection.execute("UPDATE curriculum_draft_revisions SET content=%s WHERE tenant_id=%s AND project_id=%s AND draft_id=%s",
                           (Jsonb(original), *scope[:2], draft.id))
    assert repository.activate(*scope, draft.id, activation_body()).draft == draft


@pytest.mark.parametrize("target", ["draft", "context", "source", "direct_source", "project"])
def test_complete_dependency_deletion_removes_versions_and_activation_receipts(ingestion, target):
    repository, scope, context, draft = activation_setup(ingestion)
    activated = repository.activate(*scope, draft.id, activation_body())
    second = DraftRepository(ingestion[0].store).replace(*scope, draft.id, DraftReplace(
        idempotency_key="activation-deletion-history", expected_revision=1, content=content_for(context)))
    repository.activate(*scope, draft.id, activation_body("activation-deletion-version-two", second.revision))
    if target == "draft":
        DraftRepository(ingestion[0].store).delete(*scope, draft.id)
    elif target == "context":
        ContextRepository(ingestion[0].store).delete(*scope, context.id)
    elif target == "source":
        ingestion[0].delete_source(*scope[:2], context.request.selected_sources[0].source_id, scope[2])
    elif target == "direct_source":
        with ingestion[0].store._connect() as connection:
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (*scope[:2], context.request.selected_sources[0].source_id))
    else:
        ingestion[1].delete_project(ingestion[2], scope[1])
    assert version_count(ingestion) == 0 and counts(ingestion) == [0, 0, 0]
    for operation in [lambda: repository.read(*scope, activated.id),
                      lambda: repository.latest(*scope, draft.id),
                      lambda: repository.activate(*scope, draft.id, activation_body())]:
        with pytest.raises(ProjectNotFoundError):
            operation()


@pytest.mark.parametrize("target", ["document", "direct_approval", "snapshot"])
@pytest.mark.parametrize("cited", [False, True])
def test_historical_document_cleanup_removes_activated_versions_even_after_head_drops_it(ingestion, target, cited):
    drafts, documents, scope, context, document, fetcher = document_setup(ingestion)
    body = draft_request(context, document) if cited else draft_request(context, ids=[document.id])
    first = drafts.create(*scope, context.id, body)
    repository = AssignmentRepository(ingestion[0].store)
    old = repository.activate(*scope, first.id, activation_body())
    second = drafts.replace(*scope, first.id, DraftReplace(idempotency_key="drop-activated-document",
                            expected_revision=1, content=content_for(context), documentation_ids=[]))
    latest = repository.activate(*scope, first.id, activation_body("activate-without-document", 2))
    assert old.draft == first and latest.draft == second
    if target == "document":
        documents.delete(*scope, document.id)
    else:
        table, column = ("curriculum_document_approvals", "id") if target == "direct_approval" else (
            "curriculum_document_snapshots", "document_id")
        with ingestion[0].store._connect() as connection:
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=%s AND project_id=%s AND {column}=%s",
                               (*scope[:2], document.id))
    assert version_count(ingestion) == 0 and counts(ingestion) == [0, 0, 0]
    assert fetcher.calls == [document.policy.id]
    for identity in [old.id, latest.id]:
        with pytest.raises(ProjectNotFoundError):
            repository.read(*scope, identity)


def test_concurrent_same_or_distinct_keys_activate_current_revision_only_once(ingestion):
    repository, scope, _, draft = activation_setup(ingestion)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = list(pool.map(lambda _: repository.activate(*scope, draft.id, activation_body()), range(2)))
    assert first[0] == first[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        other = list(pool.map(lambda index: repository.activate(*scope, draft.id,
                          activation_body(f"concurrent-new-activation-{index}")), range(2)))
    assert other == [first[0], first[0]]
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 1, 4]


def test_direct_version_removal_cascades_only_its_activation_receipts(ingestion):
    repository, scope, _, draft = activation_setup(ingestion)
    activated = repository.activate(*scope, draft.id, activation_body())
    repository.activate(*scope, draft.id, activation_body("second-key-same-version"))
    assert counts(ingestion) == [1, 1, 3]
    with ingestion[0].store._connect() as connection:
        connection.execute("DELETE FROM curriculum_assignment_versions WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (*scope[:2], activated.id))
    assert version_count(ingestion) == 0 and counts(ingestion) == [1, 1, 1]
    assert DraftRepository(ingestion[0].store).read(*scope, draft.id) == draft
    assert repository.latest(*scope, draft.id) is None
    with pytest.raises(ProjectNotFoundError):
        repository.read(*scope, activated.id)


def test_new_activation_waits_for_inflight_direct_version_delete_and_creates_fresh_receipt(ingestion, monkeypatch):
    repository, scope, _, draft = activation_setup(ingestion)
    old = repository.activate(*scope, draft.id, activation_body())
    deleted, release = Event(), Event()
    name = "activation-version-delete-" + uuid4().hex
    original = ingestion[0].store._connect

    def named_connection():
        connection = original()
        if current_thread().name.startswith("assignment-version-race"):
            connection.execute("SELECT set_config('application_name',%s,false)", (name,))
        return connection

    def remove():
        with original() as connection:
            connection.execute("SET LOCAL lock_timeout='5s'")
            connection.execute("DELETE FROM curriculum_assignment_versions WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (*scope[:2], old.id))
            deleted.set()
            assert release.wait(10)

    monkeypatch.setattr(ingestion[0].store, "_connect", named_connection)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="assignment-version-race") as pool:
        deletion = pool.submit(remove)
        try:
            assert deleted.wait(10)
            pending = pool.submit(repository.activate, *scope, draft.id, activation_body("new-key-after-version-delete"))
            assert wait_for_lock(ingestion[0].store, name, pending)
        finally:
            release.set()
        deletion.result(timeout=10)
        accepted = pending.result(timeout=10)
    assert accepted.id != old.id and accepted.draft == draft
    assert repository.read(*scope, accepted.id) == accepted
    assert version_count(ingestion) == 1 and counts(ingestion) == [1, 1, 2]
    with pytest.raises(ProjectNotFoundError):
        repository.read(*scope, old.id)


def test_failed_activation_response_binding_rolls_back_version_and_command(ingestion, monkeypatch):
    repository, scope, _, draft = activation_setup(ingestion)
    original = AssignmentRepository._view

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise SourceError("synthetic_activation_failure", "Synthetic activation failure.", 503)

    with monkeypatch.context() as patch:
        patch.setattr(AssignmentRepository, "_view", staticmethod(fail))
        with pytest.raises(SourceError) as failure:
            repository.activate(*scope, draft.id, activation_body())
        assert failure.value.code == "synthetic_activation_failure"
    assert version_count(ingestion) == 0 and counts(ingestion) == [1, 1, 1]
    assert repository.activate(*scope, draft.id, activation_body()).draft == draft


def test_simultaneous_edit_and_activation_never_accept_unreviewed_revision(ingestion):
    repository, scope, context, draft = activation_setup(ingestion)

    def activate_reviewed():
        try:
            return repository.activate(*scope, draft.id, activation_body())
        except SourceError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        activation = pool.submit(activate_reviewed)
        edit = pool.submit(DraftRepository(ingestion[0].store).replace, *scope, draft.id, DraftReplace(
            idempotency_key="concurrent-activation-edit", expected_revision=1,
            content=content_for(context, title="Unreviewed concurrent revision")))
        result = activation.result(timeout=10)
        assert edit.result(timeout=10).revision == 2
    if isinstance(result, SourceError):
        assert result.code == "draft_revision_conflict" and version_count(ingestion) == 0
    else:
        assert result.revision == 1 and result.draft == draft
        assert repository.read(*scope, result.id) == result and version_count(ingestion) == 1


@pytest.mark.parametrize("table,column", [("curriculum_document_approvals", "id"),
                                         ("curriculum_document_snapshots", "document_id")])
def test_direct_document_delete_waits_for_activation_and_cleans_all_results(ingestion, monkeypatch, table, column):
    drafts, _, scope, context, document, _ = document_setup(ingestion)
    draft = drafts.create(*scope, context.id, draft_request(context, document))
    repository = AssignmentRepository(ingestion[0].store)
    entered, release, deleting = Event(), Event(), Event()
    name = "activation-document-fence-" + uuid4().hex
    original = DraftRepository._bind

    def pause(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(10)
        return result

    def remove():
        with ingestion[0].store._connect() as connection:
            connection.execute("SET LOCAL lock_timeout='5s'")
            connection.execute("SELECT set_config('application_name',%s,false)", (name,))
            deleting.set()
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=%s AND project_id=%s AND {column}=%s",
                               (*scope[:2], document.id))

    monkeypatch.setattr(DraftRepository, "_bind", staticmethod(pause))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.activate, *scope, draft.id, activation_body())
        try:
            assert entered.wait(10)
            deletion = pool.submit(remove)
            assert deleting.wait(10)
            assert wait_for_lock(ingestion[0].store, name, deletion)
        finally:
            release.set()
        accepted = pending.result(timeout=10)
        deletion.result(timeout=10)
    assert version_count(ingestion) == 0 and counts(ingestion) == [0, 0, 0]
    with pytest.raises(ProjectNotFoundError):
        repository.read(*scope, accepted.id)


@pytest.mark.parametrize("winner", ["activation", "deletion"])
def test_activation_after_historical_document_drop_serializes_with_direct_delete(ingestion, monkeypatch, winner):
    drafts, _, scope, context, document, _ = document_setup(ingestion)
    draft = drafts.create(*scope, context.id, draft_request(context, document))
    drafts.replace(*scope, draft.id, DraftReplace(idempotency_key="historical-document-removed",
                   expected_revision=1, content=content_for(context), documentation_ids=[]))
    repository = AssignmentRepository(ingestion[0].store)
    entered, release, deleting = Event(), Event(), Event()
    name = "activation-historical-delete-" + uuid4().hex
    point = "_bind" if winner == "activation" else "_documents"
    original = getattr(DraftRepository, point)

    def pause(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(10)
        return result

    def remove():
        with ingestion[0].store._connect() as connection:
            connection.execute("SET LOCAL lock_timeout='5s'")
            connection.execute("SELECT set_config('application_name',%s,false)", (name,))
            deleting.set()
            connection.execute("DELETE FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (*scope[:2], document.id))

    monkeypatch.setattr(DraftRepository, point, staticmethod(pause))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.activate, *scope, draft.id, activation_body(revision=2))
        try:
            assert entered.wait(10)
            deletion = pool.submit(remove)
            assert deleting.wait(10)
            if winner == "activation":
                assert wait_for_lock(ingestion[0].store, name, deletion)
            else:
                deletion.result(timeout=5)
        finally:
            release.set()
        if winner == "activation":
            assert pending.result(timeout=10).revision == 2
            deletion.result(timeout=10)
        else:
            with pytest.raises(ProjectNotFoundError):
                pending.result(timeout=10)
    assert version_count(ingestion) == 0 and counts(ingestion) == [0, 0, 0]
