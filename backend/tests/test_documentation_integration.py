"""Explicit document consent, detached HTTP capture and durable deletion fences.

All documentation bodies below are authored synthetic text; no Internet content
or model is fetched by these tests.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Event
from uuid import uuid4

from psycopg import sql
import pytest

from app.curriculum.documentation import DocumentApprove, DocumentCapture, DocumentRepository
from app.curriculum.documentation_fetch import DocumentationFetchError, FetchedDocument, get_document
from app.curriculum.repository import ContextRepository
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_curriculum_contexts_integration import wait_for_lock
from test_curriculum_drafts_integration import saved_context
from test_ingestion_integration import ingestion, run
from test_postgres_integration import isolated_postgres_url


pytestmark = pytest.mark.integration
CATALOG_ID = "fastapi-first-steps-en"
PRIVATE_TEXT = "Authored documentation: define a path operation with FastAPI. Türkçe örnek."


class SyntheticFetcher:
    def __init__(self, *, text=PRIVATE_TEXT, before_return=None):
        self.text, self.before_return = text, before_return
        self.calls = []

    def fetch(self, catalog_id):
        self.calls.append(catalog_id)
        if self.before_return is not None:
            self.before_return()
        policy = get_document(catalog_id)
        raw = ("<main>" + self.text + "</main>").encode()
        return FetchedDocument(
            catalog_id=catalog_id, parser_version=policy.parser_version,
            text=self.text, content_sha256=sha256(self.text.encode()).hexdigest(),
            raw_sha256=sha256(raw).hexdigest(), raw_bytes=len(raw), detected_version=None,
        )


def approve_body(*, key="documentation-approval-key", **changes):
    policy = get_document(CATALOG_ID)
    return DocumentApprove(**({
        "idempotency_key": key, "catalog_id": CATALOG_ID,
        "catalog_sha256": policy.fingerprint, "consent": "retrieve_and_retain",
    } | changes))


def repository_for(ingestion):
    sources, _, principal, project, actor = ingestion
    return DocumentRepository(sources.store), (principal.tenant_id, project.id, actor)


def approved_document(ingestion, *, context=None, key="documentation-approval-key"):
    context = context or saved_context(ingestion, allow_external_documentation=True)
    repository, scope = repository_for(ingestion)
    approved = repository.approve(*scope, context.id, approve_body(key=key))
    return repository, scope, context, approved


def document_counts(ingestion):
    """Include child receipts without coupling tests to the number of relations."""
    sources, _, principal, project, _ = ingestion
    with sources.store._connect() as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
            "AND tablename LIKE 'curriculum_document%' ORDER BY tablename"
        ).fetchall()
        assert tables, "The documentation migration must create project-owned relations"
        return {row["tablename"]: connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE tenant_id=%s AND project_id=%s")
            .format(sql.Identifier(row["tablename"])), (principal.tenant_id, project.id),
        ).fetchone()["count"] for row in tables}


def test_catalog_approval_list_and_read_never_fetch_or_touch_artifacts(ingestion):
    sources, _, principal, project, actor = ingestion
    context = saved_context(ingestion, allow_external_documentation=True)
    sources.artifacts.fail_get = sources.artifacts.fail_put = True
    repository, scope = repository_for(ingestion)
    catalog = repository.catalog(*scope)
    assert catalog
    approved = repository.approve(*scope, context.id, approve_body())
    assert approved.status == "pending" and approved.snapshot is None
    assert approved.failure_code is None and approved.raw_sha256 is None and approved.raw_bytes is None
    assert (approved.tenant_id, approved.project_id, approved.context_id, approved.approved_by) == (
        principal.tenant_id, project.id, context.id, actor,
    )
    assert approved.approved_at.tzinfo is not None
    assert repository.read(*scope, approved.id) == approved
    assert repository.list(*scope, context.id) == [approved]
    replayed_approval = repository.approve(*scope, context.id, approve_body())
    assert (replayed_approval.id, replayed_approval.policy, replayed_approval.approved_at) == (
        approved.id, approved.policy, approved.approved_at,
    )


def test_capture_is_immutable_scoped_and_replayed_without_another_fetch(ingestion):
    repository, scope, context, approved = approved_document(ingestion)
    fetcher = SyntheticFetcher()
    command = DocumentCapture(idempotency_key="capture-document-key")
    saved = repository.capture(*scope, approved.id, command, fetcher)
    assert saved.status == "captured" and saved.failure_code is None
    snapshot = saved.snapshot
    assert snapshot is not None and snapshot.detected_version is None
    assert snapshot.tenant_id == scope[0] and snapshot.project_id == scope[1]
    assert snapshot.url == get_document(CATALOG_ID).url
    assert snapshot.retrieved_at.tzinfo is not None and snapshot.retrieved_at >= approved.approved_at
    assert snapshot.content_sha256 == sha256(PRIVATE_TEXT.encode()).hexdigest()
    assert "".join(excerpt.text for excerpt in snapshot.excerpts) == PRIVATE_TEXT
    assert len({excerpt.id for excerpt in snapshot.excerpts}) == len(snapshot.excerpts)
    assert all(excerpt.content_sha256 == sha256(excerpt.text.encode()).hexdigest() for excerpt in snapshot.excerpts)
    raw = ("<main>" + PRIVATE_TEXT + "</main>").encode()
    assert saved.raw_sha256 == sha256(raw).hexdigest() and saved.raw_bytes == len(raw)
    assert repository.capture(*scope, approved.id, command, fetcher) == saved
    assert repository.read(*scope, approved.id) == saved
    assert fetcher.calls == [CATALOG_ID]
    # A browser's mutable response cannot rewrite stored text or evidence IDs.
    snapshot.excerpts[0].text = "Caller mutated response"
    restored = repository.read(*scope, approved.id)
    assert "".join(excerpt.text for excerpt in restored.snapshot.excerpts) == PRIVATE_TEXT
    assert restored.context_id == context.id


def test_approval_key_binds_context_and_catalog_policy(ingestion):
    repository, scope, context, approved = approved_document(ingestion)
    other = saved_context(ingestion, key="other-doc-context", allow_external_documentation=True)
    assert repository.approve(*scope, context.id, approve_body()) == approved
    with pytest.raises(SourceError) as conflict:
        repository.approve(*scope, other.id, approve_body())
    assert conflict.value.code == "idempotency_conflict" and conflict.value.status == 409
    assert repository.list(*scope, other.id) == []
    assert repository.list(*scope, context.id) == [approved]


@pytest.mark.parametrize("invalid", ["permission", "catalog", "policy"])
def test_unapproved_or_stale_document_cannot_be_saved_or_fetched(ingestion, invalid):
    context = saved_context(ingestion, allow_external_documentation=invalid != "permission")
    repository, scope = repository_for(ingestion)
    changes = {"catalog_id": "unapproved-document"} if invalid == "catalog" else (
        {"catalog_sha256": "0" * 64} if invalid == "policy" else {})
    with pytest.raises(SourceError) as rejected:
        repository.approve(*scope, context.id, approve_body(**changes))
    assert rejected.value.status in {409, 422}
    assert repository.list(*scope, context.id) == []
    assert not any(document_counts(ingestion).values())


def test_every_repository_operation_requires_both_scopes_and_current_membership(ingestion):
    sources, service, principal, project, actor = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    foreign = AuthenticatedPrincipal(provider="test", subject="foreign-document-user", tenant_id="foreign-documents")
    foreign_actor = sources.store.bootstrap_principal(foreign)
    other_project = service.create_project(principal, ProjectCreate(title="Other document scope"))
    fetcher = SyntheticFetcher()
    wrong_scopes = [(foreign.tenant_id, project.id, foreign_actor),
                    (principal.tenant_id, other_project.id, actor),
                    (principal.tenant_id, project.id, foreign_actor)]
    for wrong in wrong_scopes:
        for operation in (
            lambda: repository.approve(*wrong, context.id, approve_body()),
            lambda: repository.list(*wrong, context.id),
            lambda: repository.read(*wrong, approved.id),
            lambda: repository.delete(*wrong, approved.id),
            lambda: repository.capture(*wrong, approved.id, DocumentCapture(idempotency_key="wrong-scope-capture"), fetcher),
        ):
            with pytest.raises(ProjectNotFoundError):
                operation()
    with sources.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    for operation in (
        lambda: repository.catalog(*scope), lambda: repository.read(*scope, approved.id),
        lambda: repository.list(*scope, context.id), lambda: repository.delete(*scope, approved.id),
        lambda: repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="revoked-capture-key"), fetcher),
    ):
        with pytest.raises(ProjectNotFoundError):
            operation()
    assert fetcher.calls == []


def test_same_tenant_member_can_read_but_cannot_reuse_another_learners_approval(ingestion):
    sources, _, principal, project, _ = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    colleague = AuthenticatedPrincipal(provider="test", subject="another-document-learner", tenant_id=principal.tenant_id)
    colleague_id = sources.store.bootstrap_principal(colleague)
    other_scope = (principal.tenant_id, project.id, colleague_id)
    assert repository.read(*other_scope, approved.id) == approved
    assert repository.list(*other_scope, context.id) == [approved]
    fetcher = SyntheticFetcher()
    with pytest.raises(ProjectNotFoundError):
        repository.capture(*other_scope, approved.id, DocumentCapture(idempotency_key="colleague-document-capture"), fetcher)
    assert fetcher.calls == []
    assert repository.read(*scope, approved.id).status == "pending"


def test_policy_change_after_approval_blocks_capture_without_rewriting_old_consent(ingestion, monkeypatch):
    repository, scope, context, approved = approved_document(ingestion)
    old_policy = get_document(CATALOG_ID)
    current_policy = replace(old_policy, title="An explicitly changed catalog policy")
    monkeypatch.setattr("app.curriculum.documentation.get_document", lambda _: current_policy)
    fetcher = SyntheticFetcher()
    with pytest.raises(SourceError) as changed:
        repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="stale-policy-capture"), fetcher)
    assert changed.value.code == "documentation_policy_changed" and changed.value.status == 409
    assert fetcher.calls == []
    assert repository.read(*scope, approved.id) == approved
    assert repository.approve(*scope, context.id, approve_body()) == approved
    new_approval = repository.approve(*scope, context.id, approve_body(
        key="explicit-new-policy-approval", catalog_sha256=current_policy.fingerprint,
    ))
    assert new_approval.policy.fingerprint == current_policy.fingerprint
    assert new_approval.id != approved.id and new_approval.status == "pending"


def test_archive_allows_saved_read_replay_delete_but_never_new_fetch(ingestion):
    _, service, principal, project, _ = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    saved = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="archive-success-capture"), SyntheticFetcher())
    pending = repository.approve(*scope, context.id, approve_body(key="archive-pending-document"))
    service.archive_project(principal, project.id)
    replayed = repository.approve(*scope, context.id, approve_body())
    assert replayed == saved
    assert (replayed.id, replayed.policy, replayed.approved_at) == (
        approved.id, approved.policy, approved.approved_at,
    )
    assert repository.read(*scope, approved.id) == saved
    fetcher = SyntheticFetcher()
    assert repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="archive-success-capture"), fetcher) == saved
    for operation in (
        lambda: repository.approve(*scope, context.id, approve_body(key="archive-new-approval")),
        lambda: repository.capture(*scope, pending.id, DocumentCapture(idempotency_key="archive-new-capture"), fetcher),
    ):
        with pytest.raises(SourceError) as blocked:
            operation()
        assert blocked.value.code == "project_archived"
    assert fetcher.calls == []
    repository.delete(*scope, approved.id)
    repository.delete(*scope, pending.id)
    assert not any(document_counts(ingestion).values())


def test_concurrent_approval_and_capture_admit_one_physical_fetch(ingestion):
    context = saved_context(ingestion, allow_external_documentation=True)
    repository, scope = repository_for(ingestion)
    with ThreadPoolExecutor(max_workers=2) as pool:
        approvals = list(pool.map(lambda _: repository.approve(*scope, context.id, approve_body()), range(2)))
    assert approvals[0] == approvals[1]
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    fetcher = SyntheticFetcher(before_return=pause)
    command = DocumentCapture(idempotency_key="concurrent-capture-key")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.capture, *scope, approvals[0].id, command, fetcher)
        try:
            assert entered.wait(10)
            during = repository.read(*scope, approvals[0].id)
            assert during.status == "capturing" and during.snapshot is None
            for key in [command.idempotency_key, "different-concurrent-capture"]:
                with pytest.raises(SourceError) as busy:
                    repository.capture(*scope, approvals[0].id, DocumentCapture(idempotency_key=key), fetcher)
                assert busy.value.status == 409
        finally:
            release.set()
        saved = pending.result(timeout=10)
    assert saved.status == "captured" and fetcher.calls == [CATALOG_ID]
    assert repository.capture(*scope, saved.id, command, fetcher) == saved


def test_successful_snapshot_accepts_new_receipt_without_refreshing_content(ingestion):
    repository, scope, _, approved = approved_document(ingestion)
    first = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="first-capture-receipt"), SyntheticFetcher())
    fetcher = SyntheticFetcher(text="A changed page must not refresh immutable evidence.")
    second = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="second-capture-receipt"), fetcher)
    assert second == first and fetcher.calls == []


def test_snapshot_splits_long_unicode_text_losslessly_and_reuses_excerpt_ids(ingestion):
    repository, scope, _, approved = approved_document(ingestion)
    text = "ş" * 7999 + "\n🧪" + "z" * 8101
    fetcher = SyntheticFetcher(text=text)
    command = DocumentCapture(idempotency_key="multiexcerpt-document-capture")
    saved = repository.capture(*scope, approved.id, command, fetcher)
    assert len(saved.snapshot.excerpts) >= 2
    assert all(1 <= len(excerpt.text) <= 8000 for excerpt in saved.snapshot.excerpts)
    assert "".join(excerpt.text for excerpt in saved.snapshot.excerpts) == text
    assert saved.snapshot.content_sha256 == sha256(text.encode()).hexdigest()
    assert repository.capture(*scope, approved.id, command, fetcher) == saved
    assert fetcher.calls == [CATALOG_ID]


@pytest.mark.parametrize("tampered", [
    {"catalog_id": "unapproved-document"}, {"parser_version": "different-parser"},
    {"content_sha256": "a" * 64}, {"text": "text\x00nul"},
    {"detected_version": "invented-version"}, {"raw_bytes": 512001},
])
def test_capture_revalidates_detached_fetch_output_before_persistence(ingestion, tampered):
    repository, scope, _, approved = approved_document(ingestion)

    class TamperedFetcher(SyntheticFetcher):
        def fetch(self, catalog_id):
            return super().fetch(catalog_id).model_copy(update=tampered)

    fetcher = TamperedFetcher()
    with pytest.raises(SourceError) as rejected:
        repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="tampered-document-capture"), fetcher)
    assert rejected.value.code == "documentation_fetch_invalid" and rejected.value.status == 422
    saved = repository.read(*scope, approved.id)
    assert saved.status == "failed" and saved.snapshot is None
    assert saved.raw_sha256 is None and saved.raw_bytes is None
    assert fetcher.calls == [CATALOG_ID]


def test_capture_admission_does_not_lock_approval_before_its_context_dependency(ingestion, monkeypatch):
    sources, _, principal, project, _ = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    original_connect = sources.store._connect
    name = "document-context-order-" + uuid4().hex

    def named_connection():
        connection = original_connect()
        connection.execute("SELECT set_config('application_name',%s,false)", (name,))
        return connection

    monkeypatch.setattr(sources.store, "_connect", named_connection)
    fetcher = SyntheticFetcher()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original_connect() as deletion:
            deletion.execute("SET LOCAL lock_timeout='3s'")
            deletion.execute(
                "SELECT id FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR UPDATE",
                (*scope[:2], context.id),
            )
            pending = pool.submit(repository.capture, *scope, approved.id,
                                  DocumentCapture(idempotency_key="capture-context-lock-order"), fetcher)
            assert wait_for_lock(sources.store, name, pending)
            # Source deletion owns the context dependency first. Capture must
            # wait without an approval lock that would invert this cascade.
            deletion.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                             (principal.tenant_id, project.id, context.request.selected_sources[0].source_id))
        with pytest.raises(ProjectNotFoundError):
            pending.result(timeout=10)
    assert fetcher.calls == []


@pytest.mark.parametrize("code,retryable,status", [
    ("documentation_fetch_timeout", True, 503), ("documentation_fetch_invalid", False, 422),
])
def test_failed_command_is_durable_and_only_new_key_explicitly_retries(ingestion, code, retryable, status):
    repository, scope, _, approved = approved_document(ingestion)

    class FailingFetcher:
        calls = 0

        def fetch(self, catalog_id):
            self.calls += 1
            raise DocumentationFetchError(code, retryable=retryable)

    fetcher = FailingFetcher()
    failed = DocumentCapture(idempotency_key="failed-capture-command")
    for _ in range(2):
        with pytest.raises(SourceError) as failure:
            repository.capture(*scope, approved.id, failed, fetcher)
        assert failure.value.code == code and failure.value.status == status
        view = repository.read(*scope, approved.id)
        assert view.status == "failed" and view.failure_code == code and view.snapshot is None
        assert view.raw_sha256 is None and view.raw_bytes is None
    assert fetcher.calls == 1
    retry = SyntheticFetcher()
    saved = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="explicit-retry-command"), retry)
    assert saved.status == "captured" and retry.calls == [CATALOG_ID]
    # The failed receipt stays failed even after a later successful attempt.
    with pytest.raises(SourceError) as old_failure:
        repository.capture(*scope, approved.id, failed, fetcher)
    assert old_failure.value.code == code and fetcher.calls == 1
    assert repository.read(*scope, approved.id) == saved


def test_capture_key_cannot_be_reused_for_another_approved_document(ingestion):
    repository, scope, context, approved = approved_document(ingestion)
    second = repository.approve(*scope, context.id, approve_body(key="another-document-approval"))
    fetcher = SyntheticFetcher()
    command = DocumentCapture(idempotency_key="project-wide-capture-key")
    repository.capture(*scope, approved.id, command, fetcher)
    with pytest.raises(SourceError) as conflict:
        repository.capture(*scope, second.id, command, fetcher)
    assert conflict.value.code == "idempotency_conflict" and conflict.value.status == 409
    assert fetcher.calls == [CATALOG_ID]
    assert repository.read(*scope, second.id).status == "pending"


def test_expired_receipt_never_refetches_and_late_old_response_cannot_replace_retry(ingestion):
    sources, _, _, _, _ = ingestion
    repository, scope, _, approved = approved_document(ingestion)
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    old_fetcher = SyntheticFetcher(text="Stale response from an expired attempt.", before_return=pause)
    command = DocumentCapture(idempotency_key="expired-document-command")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.capture, *scope, approved.id, command, old_fetcher)
        try:
            assert entered.wait(10)
            with sources.store._connect() as connection:
                connection.execute(
                    "UPDATE curriculum_document_commands SET lease_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE tenant_id=%s AND project_id=%s AND document_id=%s AND status='capturing'",
                    (*scope[:2], approved.id),
                )
            new_fetcher = SyntheticFetcher(text="Current explicitly retried document response.")
            with pytest.raises(SourceError) as expired:
                repository.capture(*scope, approved.id, command, new_fetcher)
            assert expired.value.code == "documentation_capture_lost" and new_fetcher.calls == []
            assert repository.read(*scope, approved.id).status == "failed"
            saved = repository.capture(*scope, approved.id,
                                       DocumentCapture(idempotency_key="retry-expired-document"), new_fetcher)
            assert saved.status == "captured" and new_fetcher.calls == [CATALOG_ID]
        finally:
            release.set()
        with pytest.raises(SourceError) as stale:
            pending.result(timeout=10)
        assert stale.value.code == "documentation_capture_lost"
    assert repository.read(*scope, approved.id) == saved
    assert "".join(excerpt.text for excerpt in saved.snapshot.excerpts) == new_fetcher.text


def test_final_snapshot_insert_expiry_rolls_back_evidence_and_lease_side_effects(ingestion):
    sources, _, _, _, _ = ingestion
    repository, scope, _, approved = approved_document(ingestion)
    with sources.store._connect() as connection:
        connection.execute("""CREATE FUNCTION expire_document_test_capture() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                UPDATE curriculum_document_commands
                   SET lease_expires_at=clock_timestamp()-interval '1 second'
                 WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
                   AND document_id=NEW.document_id AND status='capturing';
                RETURN NEW;
            END;
            $$""")
        connection.execute("""CREATE TRIGGER expire_document_test_capture AFTER INSERT ON curriculum_document_snapshots
                              FOR EACH ROW EXECUTE FUNCTION expire_document_test_capture()""")
    with pytest.raises(SourceError) as expired:
        repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="final-write-expiry-capture"), SyntheticFetcher())
    assert expired.value.code == "documentation_capture_lost" and expired.value.status == 409
    read = repository.read(*scope, approved.id)
    assert read.snapshot is None and read.raw_sha256 is None and read.raw_bytes is None
    with sources.store._connect() as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM curriculum_document_snapshots WHERE tenant_id=%s AND project_id=%s",
            scope[:2],
        ).fetchone()["n"] == 0
        command = connection.execute(
            "SELECT status,lease_expires_at>clock_timestamp() AS live FROM curriculum_document_commands "
            "WHERE tenant_id=%s AND project_id=%s AND document_id=%s",
            (*scope[:2], approved.id),
        ).fetchone()
        assert command["status"] == "capturing" and command["live"]


@pytest.mark.parametrize("target", ["document", "context", "source", "direct_source", "project", "archive", "membership"])
def test_network_capture_holds_no_db_locks_and_cannot_adopt_after_authority_loss(ingestion, target):
    sources, service, principal, project, actor = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    def remove_authority():
        if target == "document":
            repository.delete(*scope, approved.id)
        elif target == "context":
            ContextRepository(sources.store).delete(*scope, context.id)
        elif target == "source":
            sources.delete_source(*scope[:2], context.request.selected_sources[0].source_id, actor)
        elif target == "project":
            service.delete_project(principal, project.id)
        elif target == "archive":
            service.archive_project(principal, project.id)
        else:
            with sources.store._connect() as connection:
                if target == "membership":
                    connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
                else:
                    connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                       (*scope[:2], context.request.selected_sources[0].source_id))

    fetcher = SyntheticFetcher(before_return=pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(repository.capture, *scope, approved.id,
                              DocumentCapture(idempotency_key="capture-lost-authority"), fetcher)
        try:
            assert entered.wait(10)
            # This must complete before fetch returns; a held DB lock would
            # deadlock this test until its deterministic timeout.
            removal = pool.submit(remove_authority)
            removal.result(timeout=5)
        finally:
            release.set()
        with pytest.raises((ProjectNotFoundError, SourceError)):
            pending.result(timeout=10)
    assert fetcher.calls == [CATALOG_ID]
    if target in {"archive", "membership"}:
        if target == "archive":
            assert repository.read(*scope, approved.id).snapshot is None
    else:
        assert not any(document_counts(ingestion).values())


@pytest.mark.parametrize("target", ["document", "context", "source", "direct_source", "project"])
def test_complete_deletion_removes_snapshot_text_approval_and_retry_receipts(ingestion, target):
    sources, service, principal, project, actor = ingestion
    context = saved_context(ingestion, multiple=True, allow_external_documentation=True)
    repository, scope, _, approved = approved_document(ingestion, context=context)
    saved = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="deleted-document-capture"), SyntheticFetcher())
    assert saved.snapshot is not None and any(document_counts(ingestion).values())
    if target == "document":
        repository.delete(*scope, approved.id)
    elif target == "context":
        ContextRepository(sources.store).delete(*scope, context.id)
    elif target == "source":
        sources.delete_source(*scope[:2], context.request.selected_sources[1].source_id, actor)
    elif target == "direct_source":
        with sources.store._connect() as connection:
            connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (*scope[:2], context.request.selected_sources[1].source_id))
    else:
        service.delete_project(principal, project.id)
    assert not any(document_counts(ingestion).values())
    fetcher = SyntheticFetcher()
    for operation in (
        lambda: repository.read(*scope, approved.id), lambda: repository.delete(*scope, approved.id),
        lambda: repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="deleted-document-capture"), fetcher),
    ):
        with pytest.raises(ProjectNotFoundError):
            operation()
    assert fetcher.calls == []


def test_saved_snapshot_and_source_context_do_not_change_after_reprocessing(ingestion):
    sources, _, _, _, actor = ingestion
    repository, scope, context, approved = approved_document(ingestion)
    saved = repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="retained-document-capture"), SyntheticFetcher())
    source_id = context.request.selected_sources[0].source_id
    replacement = sources.command(*scope[:2], source_id, actor, "reprocess", "documentation-reprocess")
    assert run(sources, replacement)
    assert repository.read(*scope, approved.id) == saved
    assert ContextRepository(sources.store).read(*scope, context.id) == context


def test_document_events_never_log_text_policy_url_keys_or_headers(ingestion, caplog):
    with caplog.at_level("INFO", logger="tutorial_workspace"):
        repository, scope, context, approved = approved_document(ingestion)
        repository.capture(*scope, approved.id, DocumentCapture(idempotency_key="private-capture-key-never-log"), SyntheticFetcher())
        repository.delete(*scope, approved.id)
    messages = "\n".join(record.message for record in caplog.records)
    assert PRIVATE_TEXT not in messages
    assert "private-capture-key-never-log" not in messages
    assert "documentation-approval-key" not in messages
    assert get_document(CATALOG_ID).url not in messages
    document_events = [record.message for record in caplog.records if "documentation" in record.message]
    assert document_events
    assert all("tenant_id" in event and "project_id" in event for event in document_events)
