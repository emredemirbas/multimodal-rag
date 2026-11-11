"""Explicit captured-document bindings, immutable history and complete deletion.

The only document fetcher used here returns authored synthetic text. Binding and
replay never call a document fetcher, artifact store or model provider.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from threading import Event
from uuid import uuid4

from psycopg.types.json import Jsonb
import pytest

from app.curriculum.contracts import AssignmentContent
from app.curriculum.documentation import DocumentCapture, DocumentRepository
from app.curriculum.documentation_fetch import get_document
from app.curriculum.delivery import RunDeliveryRepository
from app.curriculum.drafts import DraftRepository
from app.curriculum.persistence import DraftCreate, DraftReplace
from app.curriculum.repository import ContextRepository
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_curriculum_contexts_integration import wait_for_lock
from test_curriculum_drafts_integration import content_for, counts, saved_context
from test_curriculum_runs_integration import create_run, read_run
from test_documentation_integration import SyntheticFetcher, approve_body, document_counts
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration
PRIVATE_DOCUMENT = "Authored extension: add a typed item endpoint. Türkçe örnek."


def setup(ingestion, *, context=None, suffix="first", text=PRIVATE_DOCUMENT, capture=True):
    sources, _, principal, project, actor = ingestion
    context = context or saved_context(
        ingestion, key="bound-document-context", allow_extensions=True,
        allow_prerequisites=True, allow_external_documentation=True,
    )
    scope = (principal.tenant_id, project.id, actor)
    documents = DocumentRepository(sources.store)
    approved = documents.approve(*scope, context.id, approve_body(key=f"bound-approval-{suffix}"))
    fetcher = SyntheticFetcher(text=text)
    document = documents.capture(*scope, approved.id,
        DocumentCapture(idempotency_key=f"bound-capture-{suffix}"), fetcher) if capture else approved
    return DraftRepository(sources.store), documents, scope, context, document, fetcher


def document_content(context, document, *, title="Synthetic documented extension", excerpt=None):
    payload = content_for(context, title=title).model_dump()
    payload["requirements"].append({
        "id": "typed-items", "label": "extension", "description": "Add a typed item endpoint.",
        "objective_ids": ["routes"], "tutorial_segment_ids": [],
        "documentation_excerpt_ids": [excerpt or document.snapshot.excerpts[0].id],
    })
    payload["acceptance_criteria"].append({
        "id": "typed-response", "description": "The item response follows the documented shape.",
        "requirement_ids": ["typed-items"],
    })
    payload["rubric"][0]["acceptance_criterion_ids"].append("typed-response")
    return AssignmentContent.model_validate(payload)


def draft_request(context, document=None, *, key="bound-draft-create", ids=None):
    return DraftCreate(idempotency_key=key,
        content=document_content(context, document) if document else content_for(context),
        documentation_ids=ids if ids is not None else ([] if document is None else [document.id]))


def dependency_count(ingestion):
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        return connection.execute(
            "SELECT count(*) AS n FROM curriculum_draft_documents WHERE tenant_id=%s AND project_id=%s",
            (principal.tenant_id, project.id),
        ).fetchone()["n"]


def test_explicit_capture_binds_authoritative_cited_projection_without_io(ingestion, caplog):
    repo, documents, scope, context, document, fetcher = setup(
        ingestion, text="A" * 8000 + PRIVATE_DOCUMENT,
    )
    sources, _, _, _, _ = ingestion
    sources.artifacts.fail_get = sources.artifacts.fail_put = True
    content = document_content(context, document, excerpt=document.snapshot.excerpts[-1].id)
    body = DraftCreate(idempotency_key="document-cited-projection", content=content,
                       documentation_ids=[document.id])
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        saved = repo.create(*scope, context.id, body)
    assert saved.documentation_ids == [document.id]
    bound = saved.assignment.documentation_snapshots
    assert len(bound) == 1 and bound[0].id == document.id
    assert bound[0].excerpts == document.snapshot.excerpts[-1:]
    assert bound[0].content_sha256 == document.snapshot.content_sha256
    assert bound[0].url == document.policy.url
    assert bound[0].retrieved_at == document.snapshot.retrieved_at
    assert bound[0].detected_version is None
    assert saved.assignment.draft.requirements[-1].label == "extension"
    assert saved.assignment.draft.requirements[-1].tutorial_segment_ids == []
    assert saved.assignment.tutorial_evidence == context.tutorial_snapshots[0].segments
    assert repo.read(*scope, saved.id) == saved
    assert repo.create(*scope, context.id, body) == saved
    assert fetcher.calls == [document.policy.id]
    assert documents.read(*scope, document.id) == document
    assert counts(ingestion) == [1, 1, 1] and dependency_count(ingestion) == 1
    content.title = "Caller mutated its input"
    bound[0].excerpts[0].text = "Caller mutated response"
    assert repo.read(*scope, saved.id).assignment.documentation_snapshots[0].excerpts == document.snapshot.excerpts[-1:]
    logs = " ".join(record.message for record in caplog.records)
    assert PRIVATE_DOCUMENT not in logs and document.policy.url not in logs
    assert "document-cited-projection" not in logs


@pytest.mark.parametrize("kind", ["omitted", "empty", "uncaptured", "missing", "other_context"])
def test_unselected_or_unavailable_document_cannot_supply_evidence_or_leave_rows(ingestion, kind):
    repo, _, scope, context, document, fetcher = setup(ingestion)
    body = draft_request(context, document)
    expected = SourceError
    if kind in {"omitted", "empty"}:
        body = DraftCreate(idempotency_key="unselected-document-draft", content=body.content)
    elif kind == "uncaptured":
        _, _, _, _, pending, _ = setup(ingestion, context=context, suffix="pending", capture=False)
        body.documentation_ids = [pending.id]
    elif kind == "missing":
        body.documentation_ids = [uuid4()]
        expected = ProjectNotFoundError
    else:
        other = saved_context(ingestion, key="unrelated-document-context", allow_extensions=True,
                              allow_external_documentation=True)
        _, _, _, _, foreign, _ = setup(ingestion, context=other, suffix="different-context")
        body.documentation_ids = [foreign.id]
        expected = ProjectNotFoundError
    with pytest.raises(expected):
        repo.create(*scope, context.id, body)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
    assert fetcher.calls == [document.policy.id]
    assert repo.create(*scope, context.id, draft_request(context, document)).revision == 1


def test_document_selection_is_canonical_and_idempotency_binds_selected_set(ingestion):
    repo, _, scope, context, first_doc, _ = setup(ingestion)
    _, _, _, _, second_doc, _ = setup(ingestion, context=context, suffix="second")
    ids = [first_doc.id, second_doc.id]
    body = draft_request(context, first_doc, ids=ids)
    first = repo.create(*scope, context.id, body)
    assert first.documentation_ids == sorted(ids, key=str)
    assert repo.create(*scope, context.id, body.model_copy(update={"documentation_ids": list(reversed(ids))})) == first
    assert dependency_count(ingestion) == 2
    with pytest.raises(SourceError) as conflict:
        repo.create(*scope, context.id, body.model_copy(update={"documentation_ids": [first_doc.id]}))
    assert conflict.value.code == "idempotency_conflict"
    assert counts(ingestion) == [1, 1, 1] and dependency_count(ingestion) == 2


def test_empty_selection_preserves_legacy_command_digest_and_explicit_replay(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion)
    repo = DraftRepository(sources.store)
    content = content_for(context)
    legacy = DraftCreate(idempotency_key="legacy-empty-documents", content=content)
    saved = repo.create(principal.tenant_id, project.id, actor, context.id, legacy)
    payload = {"operation": "create", "target": str(context.id), "expected_revision": None,
               "content": content.model_dump(mode="json")}
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with sources.store._connect() as connection:
        assert connection.execute(
            "SELECT request_sha256 FROM curriculum_draft_commands WHERE tenant_id=%s AND project_id=%s",
            (principal.tenant_id, project.id),
        ).fetchone()["request_sha256"] == digest
    assert saved.documentation_ids == [] and dependency_count(ingestion) == 0
    assert repo.create(principal.tenant_id, project.id, actor, context.id,
        legacy.model_copy(update={"documentation_ids": []})) == saved


def test_history_replays_original_document_set_after_replacement_and_archive(ingestion):
    repo, _, scope, context, first_doc, _ = setup(ingestion)
    _, _, _, _, second_doc, _ = setup(ingestion, context=context, suffix="revision-two",
                                     text="Different authored extension documentation.")
    body = draft_request(context, first_doc)
    first = repo.create(*scope, context.id, body)
    edit = DraftReplace(idempotency_key="replace-document-selection", expected_revision=1,
        content=document_content(context, second_doc, title="Second documented revision"),
        documentation_ids=[second_doc.id])
    second = repo.replace(*scope, first.id, edit)
    assert second.documentation_ids == [second_doc.id] and second.revision == 2
    assert second.assignment.documentation_snapshots == [second_doc.snapshot]
    assert repo.read(*scope, first.id, 1) == first
    ingestion[1].archive_project(ingestion[2], ingestion[3].id)
    assert repo.create(*scope, context.id, body) == first
    assert repo.replace(*scope, first.id, edit) == second
    assert repo.read(*scope, first.id) == second
    with pytest.raises(SourceError) as archived:
        repo.replace(*scope, first.id, edit.model_copy(update={
            "idempotency_key": "new-archived-doc-edit", "expected_revision": 2,
        }))
    assert archived.value.code == "project_archived"


def test_retained_policy_survives_current_catalog_metadata_change(ingestion, monkeypatch):
    repo, documents, scope, context, document, _ = setup(ingestion)
    body = draft_request(context, document)
    first = repo.create(*scope, context.id, body)
    changed = replace(get_document(document.policy.id), title="Updated catalog title",
                      parser_version="future-reviewed-parser-v2")
    monkeypatch.setattr("app.curriculum.documentation.get_document", lambda _: changed)
    assert repo.read(*scope, first.id) == first
    assert repo.create(*scope, context.id, body) == first
    assert documents.read(*scope, document.id).policy == document.policy


@pytest.mark.parametrize("table,column", [("curriculum_document_approvals", "id"),
                                         ("curriculum_document_snapshots", "document_id")])
def test_document_removal_cleans_original_run_result_without_reopening_run(ingestion, table, column):
    repo, _, scope, context, document, _ = setup(ingestion)
    run = create_run(ingestion, context=context)
    delivery = RunDeliveryRepository(ingestion[0].store)
    claim = delivery.claim(*scope[:2], run.id)
    # The existing runtime still publishes only tutorial evidence. A later
    # authorized manual edit may select a capture without enabling generation.
    published = delivery.publish_draft(claim, content_for(context))
    assert published is not None
    repo.replace(*scope, published.id, DraftReplace(idempotency_key="document-edit-of-published-draft",
        expected_revision=1, content=document_content(context, document), documentation_ids=[document.id]))
    assert read_run(ingestion, run).result_revision == 1
    with ingestion[0].store._connect() as connection:
        connection.execute(f"DELETE FROM {table} WHERE tenant_id=%s AND project_id=%s AND {column}=%s",
                           (*scope[:2], document.id))
        assert connection.execute("SELECT count(*) AS n FROM curriculum_run_results").fetchone()["n"] == 0
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
    current = read_run(ingestion, run)
    assert current.status == "succeeded" and current.result_draft_id is current.result_revision is None
    assert delivery.claim(*scope[:2], run.id) is None


@pytest.mark.parametrize("preference", ["allow_extensions", "allow_prerequisites"])
def test_external_requirement_labels_still_require_separate_learner_opt_in(ingestion, preference):
    context = saved_context(ingestion, key="document-without-topic-permission", allow_external_documentation=True)
    repo, _, scope, _, document, _ = setup(ingestion, context=context)
    content = document_content(context, document)
    content.requirements[-1].label = "extension" if preference == "allow_extensions" else "prerequisite"
    with pytest.raises(SourceError) as rejected:
        repo.create(*scope, context.id, DraftCreate(idempotency_key="missing-topic-permission",
            content=content, documentation_ids=[document.id]))
    assert rejected.value.code == "invalid_curriculum_draft"
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0


@pytest.mark.parametrize("corruption", ["text", "full_hash", "excerpt_id", "url", "scope", "policy", "time"])
def test_stored_capture_tampering_cannot_enter_draft_or_consume_retry_key(ingestion, corruption):
    repo, _, scope, context, document, _ = setup(ingestion)
    snapshot = document.snapshot.model_dump(mode="json")
    policy = document.policy.model_dump(mode="json")
    if corruption == "text":
        snapshot["excerpts"][0]["text"] = "Injected retained body"
    elif corruption == "full_hash":
        snapshot["content_sha256"] = "0" * 64
    elif corruption == "excerpt_id":
        snapshot["excerpts"][0]["id"] = str(uuid4())
    elif corruption == "url":
        snapshot["url"] = "https://fastapi.tiangolo.com/unapproved/"
    elif corruption == "scope":
        snapshot["tenant_id"] = "different-document-tenant"
    elif corruption == "policy":
        policy["url"] = "https://attacker.invalid/private"
    else:
        snapshot["retrieved_at"] = "2000-01-01T00:00:00Z"
    with ingestion[0].store._connect() as connection:
        if corruption == "policy":
            connection.execute("UPDATE curriculum_document_approvals SET policy=%s WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (Jsonb(policy), *scope[:2], document.id))
        else:
            connection.execute("UPDATE curriculum_document_snapshots SET snapshot=%s WHERE tenant_id=%s AND project_id=%s AND document_id=%s",
                               (Jsonb(snapshot), *scope[:2], document.id))
    with pytest.raises(SourceError) as rejected:
        repo.create(*scope, context.id, draft_request(context, document))
    assert rejected.value.code == "invalid_curriculum_draft"
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0


def test_scope_and_current_membership_are_required_before_document_binding(ingestion):
    repo, _, scope, context, document, _ = setup(ingestion)
    body = draft_request(context, document)
    first = repo.create(*scope, context.id, body)
    sources, service, principal, project, actor = ingestion
    other_project = service.create_project(principal, ProjectCreate(title="Other document draft scope"))
    foreign = AuthenticatedPrincipal(provider="test", subject="foreign-doc-draft-user", tenant_id="foreign-doc-draft")
    foreign_actor = sources.store.bootstrap_principal(foreign)
    for wrong in [(foreign.tenant_id, project.id, foreign_actor),
                  (principal.tenant_id, other_project.id, actor),
                  (principal.tenant_id, project.id, foreign_actor)]:
        with pytest.raises(ProjectNotFoundError):
            repo.create(*wrong, context.id, body)
        with pytest.raises(ProjectNotFoundError):
            repo.read(*wrong, first.id)
    with sources.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    with pytest.raises(ProjectNotFoundError):
        repo.create(*scope, context.id, body)
    with pytest.raises(ProjectNotFoundError):
        repo.read(*scope, first.id)
    assert counts(ingestion) == [1, 1, 1] and dependency_count(ingestion) == 1


@pytest.mark.parametrize("target", ["document", "direct_approval", "snapshot", "context", "source", "project"])
def test_deleting_any_historical_dependency_removes_entire_draft_and_receipts(ingestion, target):
    repo, documents, scope, context, document, _ = setup(ingestion)
    first = repo.create(*scope, context.id, draft_request(context, document))
    # The current revision no longer cites/selects this document. The historical
    # revision is still retained and must not survive its document's deletion.
    edit = DraftReplace(idempotency_key="remove-document-from-head", expected_revision=1,
                        content=content_for(context), documentation_ids=[])
    repo.replace(*scope, first.id, edit)
    assert dependency_count(ingestion) == 1
    sources, service, principal, project, actor = ingestion
    if target == "document":
        documents.delete(*scope, document.id)
    elif target in {"direct_approval", "snapshot"}:
        table, column = ("curriculum_document_approvals", "id") if target == "direct_approval" else (
            "curriculum_document_snapshots", "document_id")
        with sources.store._connect() as connection:
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=%s AND project_id=%s AND {column}=%s",
                               (*scope[:2], document.id))
    elif target == "context":
        ContextRepository(sources.store).delete(*scope, context.id)
    elif target == "source":
        sources.delete_source(*scope[:2], context.request.selected_sources[0].source_id, actor)
    else:
        service.delete_project(principal, project.id)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
    for operation in [lambda: repo.read(*scope, first.id), lambda: repo.read(*scope, first.id, 1),
                      lambda: repo.replace(*scope, first.id, edit)]:
        with pytest.raises(ProjectNotFoundError):
            operation()
    if target in {"context", "source", "project"}:
        assert not any(document_counts(ingestion).values())


def test_selected_but_uncited_document_is_still_a_complete_deletion_dependency(ingestion):
    repo, documents, scope, context, document, _ = setup(ingestion)
    first = repo.create(*scope, context.id, draft_request(context, ids=[document.id]))
    assert first.documentation_ids == [document.id]
    assert first.assignment.documentation_snapshots == []
    assert dependency_count(ingestion) == 1
    documents.delete(*scope, document.id)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
    with pytest.raises(ProjectNotFoundError):
        repo.read(*scope, first.id)


def test_unselected_document_delete_preserves_unrelated_draft(ingestion):
    repo, documents, scope, context, selected, _ = setup(ingestion)
    _, _, _, _, unselected, _ = setup(ingestion, context=context, suffix="unselected")
    first = repo.create(*scope, context.id, draft_request(context, selected))
    documents.delete(*scope, unselected.id)
    assert repo.read(*scope, first.id) == first
    assert counts(ingestion) == [1, 1, 1] and dependency_count(ingestion) == 1


def test_failed_append_rolls_back_selected_dependencies_and_does_not_reserve_key(ingestion, monkeypatch):
    repo, _, scope, context, document, _ = setup(ingestion)
    body = draft_request(context, document)
    original = repo._append

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise SourceError("synthetic_failure", "Synthetic transaction failure.", 503)

    with monkeypatch.context() as patch:
        patch.setattr(repo, "_append", fail)
        with pytest.raises(SourceError):
            repo.create(*scope, context.id, body)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
    assert repo.create(*scope, context.id, body).revision == 1


@pytest.mark.parametrize("operation", ["create", "replace", "read"])
@pytest.mark.parametrize("table,column", [("curriculum_document_approvals", "id"),
                                         ("curriculum_document_snapshots", "document_id")])
def test_direct_document_delete_waits_for_binding_and_cascades_without_deadlock(ingestion, monkeypatch, operation, table, column):
    repo, _, scope, context, document, _ = setup(ingestion)
    first = None if operation == "create" else repo.create(*scope, context.id, draft_request(context, document))
    entered, release, deleting = Event(), Event(), Event()
    name = "document-draft-fence-" + uuid4().hex
    original = repo._bind

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

    # _view is a classmethod; patch the class so historical reads use the same
    # controlled point as create/replace, rather than missing an instance patch.
    monkeypatch.setattr(type(repo), "_bind", staticmethod(pause))
    if operation == "create":
        call = lambda: repo.create(*scope, context.id, draft_request(context, document))
    elif operation == "replace":
        call = lambda: repo.replace(*scope, first.id, DraftReplace(idempotency_key="fenced-doc-replacement",
            expected_revision=1, content=document_content(context, document), documentation_ids=[document.id]))
    else:
        call = lambda: repo.read(*scope, first.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(call)
        try:
            assert entered.wait(10)
            deletion = pool.submit(remove)
            assert deleting.wait(10)
            assert wait_for_lock(ingestion[0].store, name, deletion)
        finally:
            release.set()
        pending.result(timeout=10)
        deletion.result(timeout=10)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0


@pytest.mark.parametrize("table,column", [("curriculum_document_approvals", "id"),
                                         ("curriculum_document_snapshots", "document_id")])
@pytest.mark.parametrize("winner", ["replacement", "deletion"])
def test_drop_last_document_and_direct_delete_are_serialized_without_foreign_key_errors(ingestion, monkeypatch, table, column, winner):
    repo, _, scope, context, document, _ = setup(ingestion)
    first = repo.create(*scope, context.id, draft_request(context, document))
    body = DraftReplace(idempotency_key="drop-last-document-race", expected_revision=1,
                        content=content_for(context), documentation_ids=[])
    entered, release, deleting = Event(), Event(), Event()
    name = "drop-document-fence-" + uuid4().hex
    # If deletion wins, pause before the new empty selection's head recheck. If
    # replacement wins, _bind runs after the head lock has fenced its revision.
    point = "_documents" if winner == "deletion" else "_bind"
    original = getattr(repo, point)

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

    monkeypatch.setattr(repo, point, pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repo.replace, *scope, first.id, body)
        try:
            assert entered.wait(10)
            deletion = pool.submit(remove)
            assert deleting.wait(10)
            if winner == "replacement":
                assert wait_for_lock(ingestion[0].store, name, deletion)
            else:
                deletion.result(timeout=5)
        finally:
            release.set()
        if winner == "replacement":
            assert pending.result(timeout=10).documentation_ids == []
            deletion.result(timeout=10)
        else:
            with pytest.raises(ProjectNotFoundError):
                pending.result(timeout=10)
    assert counts(ingestion) == [0, 0, 0] and dependency_count(ingestion) == 0
