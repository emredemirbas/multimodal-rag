"""Explicit scoped approval and immutable official-document capture receipts.

No model work, automatic capture, or draft binding occurs at this boundary.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import logging
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError

from ..postgres import PostgresStore
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .contracts import DocumentationExcerpt, DocumentationSnapshot
from .documentation_fetch import (
    CatalogDocument, DocumentationFetchError, FetchedDocument,
    catalog_documents, get_document,
)
from .persistence import Boundary
from .repository import ContextRepository


LOGGER = logging.getLogger("tutorial_workspace")
CAPTURE_LEASE_SECONDS = 45


class CatalogPolicy(Boundary):
    id: str
    title: str
    url: str
    parser_version: str
    version_policy: str
    license_name: str
    license_url: str
    license_text: str
    attribution: str
    fingerprint: str


class DocumentApprove(Boundary):
    idempotency_key: str = Field(strict=True, min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    catalog_id: str = Field(strict=True, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    catalog_sha256: str = Field(strict=True, pattern=r"^[a-f0-9]{64}$")
    consent: Literal["retrieve_and_retain"]


class DocumentCapture(Boundary):
    idempotency_key: str = Field(strict=True, min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class DocumentView(Boundary):
    id: UUID
    tenant_id: str
    project_id: UUID
    context_id: UUID
    approved_by: UUID
    approved_at: datetime
    consent: Literal["retrieve_and_retain"]
    policy: CatalogPolicy
    status: Literal["pending", "capturing", "failed", "captured"]
    failure_code: str | None
    snapshot: DocumentationSnapshot | None
    raw_sha256: str | None
    raw_bytes: int | None


@dataclass(frozen=True)
class _Claim:
    tenant: str
    project: UUID
    actor: UUID
    document: UUID
    command: UUID
    token: UUID
    policy: CatalogPolicy


def _policy(item: CatalogDocument) -> CatalogPolicy:
    return CatalogPolicy(**asdict(item), fingerprint=item.fingerprint)


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _lost() -> SourceError:
    return SourceError("documentation_capture_lost", "The documentation capture is no longer current. Start a new explicit command if appropriate.", 409)


def _failure(code: str, retryable: bool) -> SourceError:
    if code == "documentation_capture_lost":
        return _lost()
    return SourceError(code, "The approved documentation could not be captured.", 503 if retryable else 422)


class DocumentRepository:
    def __init__(self, store: PostgresStore):
        self.store = store

    @staticmethod
    def _body(body, kind):
        try:
            if not isinstance(body, kind):
                raise ValueError()
            return kind.model_validate(body.model_dump(warnings=False))
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise SourceError("invalid_documentation_command", "The documentation command could not be validated.", 422) from None

    @staticmethod
    def _context(connection, tenant, project, context_id):
        context = connection.execute(
            "SELECT request FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR KEY SHARE",
            (tenant, project, context_id),
        ).fetchone()
        if context is None:
            raise ProjectNotFoundError("curriculum context not found")
        return context

    @staticmethod
    def _document(connection, tenant, project, document_id):
        identity = connection.execute(
            "SELECT context_id FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (tenant, project, document_id),
        ).fetchone()
        if identity is None:
            raise ProjectNotFoundError("documentation not found")
        # Context/source deletion locks the parent before cascading to approval.
        # Take that same order, including callers outside the project API.
        DocumentRepository._context(connection, tenant, project, identity["context_id"])
        row = connection.execute(
            "SELECT * FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND id=%s FOR UPDATE",
            (tenant, project, document_id),
        ).fetchone()
        if row is None:
            raise ProjectNotFoundError("documentation not found")
        return row

    @staticmethod
    def _permission(context):
        if context["request"]["learner"]["allow_external_documentation"] is not True:
            raise SourceError("documentation_not_enabled", "This context does not allow external documentation.", 409)

    @staticmethod
    def _current_policy(row):
        try:
            policy = _policy(get_document(row["policy"]["id"]))
        except (DocumentationFetchError, KeyError):
            raise SourceError("documentation_policy_changed", "Choose and approve the current catalog entry before capturing.", 409) from None
        if policy.model_dump() != row["policy"]:
            raise SourceError("documentation_policy_changed", "Choose and approve the current catalog entry before capturing.", 409)
        return policy

    @staticmethod
    def _view(connection, row) -> DocumentView:
        scope = (row["tenant_id"], row["project_id"], row["id"])
        saved = connection.execute(
            "SELECT * FROM curriculum_document_snapshots WHERE tenant_id=%s AND project_id=%s AND document_id=%s", scope,
        ).fetchone()
        command = connection.execute(
            "SELECT status,failure_code FROM curriculum_document_commands WHERE tenant_id=%s AND project_id=%s AND document_id=%s ORDER BY command_no DESC LIMIT 1", scope,
        ).fetchone()
        status = "captured" if saved else (command["status"] if command else "pending")
        return DocumentView.model_validate_json(json.dumps({
            "id": str(row["id"]), "tenant_id": row["tenant_id"], "project_id": str(row["project_id"]),
            "context_id": str(row["context_id"]), "approved_by": str(row["approved_by"]),
            "approved_at": row["approved_at"].isoformat(), "consent": row["consent"], "policy": row["policy"],
            "status": status, "failure_code": command["failure_code"] if command and not saved else None,
            "snapshot": saved["snapshot"] if saved else None,
            "raw_sha256": saved["raw_sha256"] if saved else None, "raw_bytes": saved["raw_bytes"] if saved else None,
        }))

    def catalog(self, tenant, project, actor) -> list[CatalogPolicy]:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            return [_policy(item) for item in catalog_documents()]

    def approve(self, tenant, project, actor, context_id, body: DocumentApprove) -> DocumentView:
        body = self._body(body, DocumentApprove)
        digest = _digest({"actor": str(actor), "context": str(context_id), **body.model_dump(exclude={"idempotency_key"})})
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            context = self._context(connection, tenant, project, context_id)
            existing = connection.execute(
                "SELECT * FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != digest:
                    raise SourceError("idempotency_conflict", "This approval key was used for different input.", 409)
                return self._view(connection, existing)
            if state["status"] != "active":
                raise SourceError("project_archived", "Restore the project before approving documentation.", 409)
            self._permission(context)
            try:
                policy = _policy(get_document(body.catalog_id))
            except DocumentationFetchError:
                raise SourceError("documentation_not_allowed", "Select an available catalog entry.", 422) from None
            if policy.fingerprint != body.catalog_sha256:
                raise SourceError("documentation_policy_changed", "Choose and approve the current catalog entry before capturing.", 409)
            count = connection.execute(
                "SELECT count(*) AS n FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND context_id=%s",
                (tenant, project, context_id),
            ).fetchone()["n"]
            if count >= 20:
                raise SourceError("documentation_limit", "A context can retain at most twenty approved documents.", 422)
            row = connection.execute(
                """INSERT INTO curriculum_document_approvals
                   (tenant_id,project_id,id,context_id,approved_by,consent,idempotency_key,request_sha256,policy)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, uuid4(), context_id, actor, body.consent, body.idempotency_key, digest, Jsonb(policy.model_dump())),
            ).fetchone()
            view = self._view(connection, row)
        self._log("documentation_approved", tenant, project, view.id)
        return view

    def read(self, tenant, project, actor, document_id) -> DocumentView:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            # Project lock serializes document deletion; no exclusive document lock on reads.
            row = connection.execute(
                "SELECT * FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (tenant, project, document_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("documentation not found")
            return self._view(connection, row)

    def list(self, tenant, project, actor, context_id) -> list[DocumentView]:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            self._context(connection, tenant, project, context_id)
            rows = connection.execute(
                "SELECT * FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND context_id=%s ORDER BY approved_at,id",
                (tenant, project, context_id),
            ).fetchall()
            return [self._view(connection, row) for row in rows]

    def delete(self, tenant, project, actor, document_id) -> None:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=True)
            row = connection.execute(
                "DELETE FROM curriculum_document_approvals WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING id",
                (tenant, project, document_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("documentation not found")
        self._log("documentation_deleted", tenant, project, document_id)

    @staticmethod
    def _expire(connection, tenant, project, document_id):
        connection.execute(
            """UPDATE curriculum_document_commands SET status='failed',finished_at=clock_timestamp(),
                      failure_code='documentation_capture_lost',retryable=true
               WHERE tenant_id=%s AND project_id=%s AND document_id=%s AND status='capturing'
                 AND lease_expires_at<=clock_timestamp()""", (tenant, project, document_id),
        )

    def _begin(self, tenant, project, actor, document_id, body):
        digest = _digest({"actor": str(actor), "document": str(document_id)})
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            # All mutations acquire the project first. Context is a deletion dependency.
            row = self._document(connection, tenant, project, document_id)
            context = self._context(connection, tenant, project, row["context_id"])
            if row["approved_by"] != actor:
                raise ProjectNotFoundError("documentation not found")
            existing = connection.execute(
                "SELECT * FROM curriculum_document_commands WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if existing and existing["request_sha256"] != digest:
                raise SourceError("idempotency_conflict", "This capture key was used for different input.", 409)
            # Seal expiry even on replay; return errors outside this transaction so it commits.
            self._expire(connection, tenant, project, document_id)
            if existing:
                existing = connection.execute(
                    "SELECT * FROM curriculum_document_commands WHERE tenant_id=%s AND project_id=%s AND id=%s",
                    (tenant, project, existing["id"]),
                ).fetchone()
                if existing["status"] == "succeeded":
                    return self._view(connection, row)
                if existing["status"] == "failed":
                    return _failure(existing["failure_code"], existing["retryable"])
                return SourceError("documentation_capture_in_progress", "This document already has a capture in progress.", 409)
            if state["status"] != "active":
                return SourceError("project_archived", "Restore the project before capturing documentation.", 409)
            self._permission(context)
            policy = self._current_policy(row)
            view = self._view(connection, row)
            if view.status == "capturing":
                return SourceError("documentation_capture_in_progress", "This document already has a capture in progress.", 409)
            command_no = connection.execute(
                "SELECT coalesce(max(command_no),0)+1 AS n FROM curriculum_document_commands WHERE tenant_id=%s AND project_id=%s AND document_id=%s",
                (tenant, project, document_id),
            ).fetchone()["n"]
            command, token = uuid4(), uuid4()
            captured = view.snapshot is not None
            connection.execute(
                """INSERT INTO curriculum_document_commands
                   (tenant_id,project_id,id,document_id,actor_user_id,idempotency_key,request_sha256,
                    command_no,status,lease_token,lease_expires_at,finished_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           clock_timestamp()+make_interval(secs=>%s),CASE WHEN %s THEN clock_timestamp() END)""",
                (tenant, project, command, document_id, actor, body.idempotency_key, digest, command_no,
                 "succeeded" if captured else "capturing", token, CAPTURE_LEASE_SECONDS, captured),
            )
            return view if captured else _Claim(tenant, project, actor, document_id, command, token, policy)

    def _live(self, connection, claim):
        state = ContextRepository._scope(connection, claim.tenant, claim.project, claim.actor, write=True)
        row = self._document(connection, claim.tenant, claim.project, claim.document)
        context = self._context(connection, claim.tenant, claim.project, row["context_id"])
        if (state["status"] != "active" or row["approved_by"] != claim.actor
                or context["request"]["learner"]["allow_external_documentation"] is not True
                or row["policy"] != claim.policy.model_dump()):
            raise _lost()
        if self._current_policy(row) != claim.policy:
            raise _lost()
        current = connection.execute(
            """SELECT id FROM curriculum_document_commands WHERE tenant_id=%s AND project_id=%s
               AND id=%s AND document_id=%s AND lease_token=%s AND status='capturing'
               AND lease_expires_at>clock_timestamp() FOR UPDATE""",
            (claim.tenant, claim.project, claim.command, claim.document, claim.token),
        ).fetchone()
        if current is None:
            raise _lost()
        return row

    @staticmethod
    def _complete(connection, claim, *, failure=None):
        code, retryable = (failure.code, failure.retryable) if failure else (None, None)
        row = connection.execute(
            """UPDATE curriculum_document_commands SET status=%s,finished_at=clock_timestamp(),failure_code=%s,retryable=%s
               WHERE tenant_id=%s AND project_id=%s AND id=%s AND document_id=%s AND lease_token=%s
                 AND status='capturing' AND lease_expires_at>clock_timestamp() RETURNING id""",
            ("failed" if failure else "succeeded", code, retryable, claim.tenant, claim.project,
             claim.command, claim.document, claim.token),
        ).fetchone()
        if row is None:
            raise _lost()

    def _finish(self, claim, fetched):
        try:
            with self.store._connect() as connection:
                row = self._live(connection, claim)
                retrieved_at = connection.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
                excerpts = []
                for index, offset in enumerate(range(0, len(fetched.text), 8000)):
                    text = fetched.text[offset:offset + 8000]
                    digest = sha256(text.encode("utf-8")).hexdigest()
                    excerpts.append(DocumentationExcerpt(id=uuid5(claim.document, f"excerpt:{index}:{digest}"),
                                                        text=text, content_sha256=digest))
                snapshot = DocumentationSnapshot(
                    id=claim.document, tenant_id=claim.tenant, project_id=claim.project,
                    url=claim.policy.url, retrieved_at=retrieved_at, detected_version=fetched.detected_version,
                    content_sha256=fetched.content_sha256, excerpts=excerpts,
                )
                connection.execute(
                    """INSERT INTO curriculum_document_snapshots (tenant_id,project_id,document_id,snapshot,raw_sha256,raw_bytes)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (claim.tenant, claim.project, claim.document, Jsonb(snapshot.model_dump(mode="json")),
                     fetched.raw_sha256, fetched.raw_bytes),
                )
                # A final clock check also fences delays in snapshot writes/triggers.
                self._complete(connection, claim)
                return self._view(connection, row)
        except ProjectNotFoundError:
            raise _lost() from None
        except SourceError as error:
            if error.code == "documentation_policy_changed":
                raise _lost() from None
            raise

    def _fail(self, claim, error):
        try:
            with self.store._connect() as connection:
                self._live(connection, claim)
                self._complete(connection, claim, failure=error)
        except (ProjectNotFoundError, SourceError):
            raise _lost() from None

    def capture(self, tenant, project, actor, document_id, body: DocumentCapture, fetcher) -> DocumentView:
        body = self._body(body, DocumentCapture)
        claim = self._begin(tenant, project, actor, document_id, body)
        if isinstance(claim, SourceError):
            raise claim
        if isinstance(claim, DocumentView):
            return claim
        started = perf_counter()
        self._log("documentation_capture_started", tenant, project, document_id)
        try:
            try:
                result = fetcher.fetch(claim.policy.id)
                if not isinstance(result, FetchedDocument):
                    raise ValueError()
                fetched = FetchedDocument.model_validate(result.model_dump(warnings=False))
                if fetched.catalog_id != claim.policy.id or fetched.parser_version != claim.policy.parser_version:
                    raise ValueError()
            except DocumentationFetchError:
                raise
            except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
                raise DocumentationFetchError("documentation_fetch_invalid", retryable=False) from None
            except Exception:
                raise DocumentationFetchError("documentation_fetch_unavailable", retryable=True) from None
            try:
                view = self._finish(claim, fetched)
            except (ValidationError, ValueError):
                raise DocumentationFetchError("documentation_fetch_invalid", retryable=False) from None
        except DocumentationFetchError as error:
            self._fail(claim, error)
            self._log("documentation_capture_failed", tenant, project, document_id, code=error.code,
                      duration_ms=round((perf_counter() - started) * 1000))
            raise _failure(error.code, error.retryable) from None
        except SourceError as error:
            self._log("documentation_capture_discarded", tenant, project, document_id, code=error.code)
            raise
        self._log("documentation_capture_committed", tenant, project, document_id,
                  duration_ms=round((perf_counter() - started) * 1000), raw_bytes=view.raw_bytes,
                  excerpt_count=len(view.snapshot.excerpts))
        return view

    @staticmethod
    def _log(event, tenant, project, document, **fields):
        LOGGER.info(json.dumps({"event": event, "tenant_id": tenant, "project_id": str(project),
                                "document_id": str(document), **fields}))
