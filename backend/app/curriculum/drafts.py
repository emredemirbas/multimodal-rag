"""Version editable drafts against saved tutorial and explicitly selected document evidence."""

import hashlib
import json
import logging
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..postgres import PostgresStore
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .contracts import AssignmentContent, AssignmentDraft, DocumentationSnapshot
from .documentation import CatalogPolicy
from .documentation_fetch import MAX_RAW_BYTES, MAX_TEXT_BYTES, catalog_documents
from .persistence import (
    MAX_DRAFT_STORAGE_BYTES,
    DraftCreate,
    DraftReplace,
    DraftRevisionView,
)
from .repository import ContextRepository
from .validation import CurriculumValidationError, bind_assignment


LOGGER = logging.getLogger("tutorial_workspace")
# Binding policy grants no network capability. Retain exact reviewed URLs rather
# than deriving allowed hosts from database policy or model-supplied metadata.
_DOCUMENT_URLS = {item.id: item.url for item in catalog_documents()}


class DraftRepository:
    def __init__(self, store: PostgresStore):
        self.store = store

    @staticmethod
    def _invalid():
        return SourceError("invalid_curriculum_draft", "The assignment draft could not be validated.", 422)

    @classmethod
    def _body(cls, contract, body):
        try:
            if not isinstance(body, contract):
                raise ValueError()
            return contract.model_validate_json(body.model_dump_json(warnings=False))
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise cls._invalid() from None

    @classmethod
    def _payload(cls, content: AssignmentContent):
        try:
            payload = content.model_dump(mode="json")

            def compatible(value):
                if isinstance(value, str):
                    return "\x00" not in value
                if isinstance(value, list):
                    return all(compatible(item) for item in value)
                if isinstance(value, dict):
                    return all(compatible(item) for item in value.values())
                return True

            # Match jsonb's spaced representation; no truncation or partial write.
            if (not compatible(payload)
                    or len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_DRAFT_STORAGE_BYTES):
                raise ValueError()
            return payload
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
            raise cls._invalid() from None

    @staticmethod
    def _hash(operation, target, expected_revision, payload, documentation_ids=None):
        value = {"operation": operation, "target": str(target),
                 "expected_revision": expected_revision, "content": payload}
        # Preserve all historical empty-selection command hashes, including callers
        # using the current repository against a populated pre-0026 upgrade schema.
        if documentation_ids:
            value["documentation_ids"] = sorted(map(str, documentation_ids))
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _context(connection, tenant, project, context_id):
        # Source deletion's trigger must acquire this row before deleting its
        # context/revisions. Do not acquire source locks after this context lock:
        # direct source DELETE takes them in the opposite order.
        row = connection.execute(
            """SELECT * FROM curriculum_contexts
               WHERE tenant_id=%s AND project_id=%s AND id=%s FOR KEY SHARE""",
            (tenant, project, context_id),
        ).fetchone()
        if row is None:
            raise ProjectNotFoundError("curriculum context not found")
        return ContextRepository._view(row)

    @classmethod
    def _bind(cls, tenant, project, context, content, documentation_snapshots=None):
        try:
            draft = AssignmentDraft(tenant_id=tenant, project_id=project, **content.model_dump())
            documents = documentation_snapshots if documentation_snapshots is not None else []
            hosts = frozenset(urlsplit(value).hostname for value in _DOCUMENT_URLS.values())
            return bind_assignment(context.request, draft, context.tutorial_snapshots, documents,
                                   allowed_document_hosts=hosts)
        except (CurriculumValidationError, ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise cls._invalid() from None

    @classmethod
    def _documents(cls, connection, tenant, project, context, documentation_ids):
        """Read only explicitly selected, captured copies under deletion fences.

        The caller already holds the immutable context. Approval and snapshot
        locks precede draft/revision/FK locks, matching direct document deletion.
        This method performs no fetch and does not consult live page contents.
        """
        if not documentation_ids:
            return []
        if context.request.learner.allow_external_documentation is not True:
            raise cls._invalid()
        snapshots = []
        for document_id in sorted(documentation_ids, key=str):
            row = connection.execute(
                """SELECT * FROM curriculum_document_approvals
                   WHERE tenant_id=%s AND project_id=%s AND context_id=%s AND id=%s FOR KEY SHARE""",
                (tenant, project, context.id, document_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum documentation not found")
            saved = connection.execute(
                """SELECT * FROM curriculum_document_snapshots
                   WHERE tenant_id=%s AND project_id=%s AND document_id=%s FOR KEY SHARE""",
                (tenant, project, document_id),
            ).fetchone()
            try:
                if saved is None:
                    raise ValueError()
                policy = CatalogPolicy.model_validate(row["policy"], strict=True)
                policy_values = policy.model_dump(exclude={"fingerprint"})
                digest = hashlib.sha256(json.dumps(policy_values, sort_keys=True,
                                                  separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
                if (policy.fingerprint != digest or policy.url != _DOCUMENT_URLS.get(policy.id)
                        or any(not isinstance(value, str) or not value.strip() or "\x00" in value
                               for value in policy_values.values())
                        or row["consent"] != "retrieve_and_retain"
                        or not isinstance(row["approved_by"], UUID)
                        or row["approved_at"].tzinfo is None or row["approved_at"].utcoffset() is None
                        or type(saved["raw_bytes"]) is not int or not 1 <= saved["raw_bytes"] <= MAX_RAW_BYTES
                        or type(saved["raw_sha256"]) is not str
                        or re.fullmatch(r"[a-f0-9]{64}", saved["raw_sha256"]) is None):
                    raise ValueError()
                snapshot = DocumentationSnapshot.model_validate_json(json.dumps(saved["snapshot"]), strict=True)
                text = "".join(excerpt.text for excerpt in snapshot.excerpts)
                encoded = text.encode("utf-8")
                if (snapshot.id != document_id or (snapshot.tenant_id, snapshot.project_id) != (tenant, project)
                        or snapshot.url != policy.url or snapshot.detected_version is not None
                        or snapshot.retrieved_at < row["approved_at"] or not text.strip() or "\x00" in text
                        or len(encoded) > MAX_TEXT_BYTES
                        or hashlib.sha256(encoded).hexdigest() != snapshot.content_sha256):
                    raise ValueError()
                # Capture splits losslessly at 8,000 characters and owns each
                # UUID5. Rechecking defeats altered IDs or reordered fragments.
                for index, excerpt in enumerate(snapshot.excerpts):
                    if (excerpt.text != text[index * 8000:(index + 1) * 8000]
                            or excerpt.id != uuid5(document_id, f"excerpt:{index}:{excerpt.content_sha256}")):
                        raise ValueError()
                snapshots.append(snapshot)
            except (ValidationError, ValueError, TypeError, AttributeError, KeyError, RecursionError, UnicodeError):
                raise cls._invalid() from None
        return snapshots

    @classmethod
    def _view(cls, connection, tenant, project, row, *, context=None):
        if context is None:
            context = cls._context(connection, tenant, project, row["context_id"])
        try:
            documentation_ids = [UUID(str(value)) for value in row.get("documentation_ids", [])]
            if (len(documentation_ids) > 20 or len(set(documentation_ids)) != len(documentation_ids)
                    or documentation_ids != sorted(documentation_ids, key=str)):
                raise ValueError()
            documents = cls._documents(connection, tenant, project, context, documentation_ids)
            if documentation_ids:
                references = connection.execute(
                    """SELECT document_id FROM curriculum_draft_documents
                       WHERE tenant_id=%s AND project_id=%s AND context_id=%s AND draft_id=%s AND revision=%s
                       ORDER BY document_id""",
                    (tenant, project, row["context_id"], row["draft_id"], row["revision"]),
                ).fetchall()
                if [item["document_id"] for item in references] != documentation_ids:
                    raise ValueError()
            content = AssignmentContent.model_validate_json(json.dumps(row["content"]))
            assignment = cls._bind(tenant, project, context, content, documents)
            return DraftRevisionView(
                id=row["draft_id"], tenant_id=tenant, project_id=project,
                context_id=row["context_id"], revision=row["revision"],
                created_at=row["created_at"], assignment=assignment, documentation_ids=documentation_ids,
            )
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise cls._invalid() from None

    @classmethod
    def _replay(cls, connection, tenant, project, key, digest):
        row = connection.execute(
            """SELECT c.request_sha256,r.*,d.context_id FROM curriculum_draft_commands c
               JOIN curriculum_draft_revisions r ON r.tenant_id=c.tenant_id
                 AND r.project_id=c.project_id AND r.draft_id=c.draft_id AND r.revision=c.revision
               JOIN curriculum_drafts d ON d.tenant_id=r.tenant_id
                 AND d.project_id=r.project_id AND d.id=r.draft_id
               WHERE c.tenant_id=%s AND c.project_id=%s AND c.idempotency_key=%s""",
            (tenant, project, key),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != digest:
            raise SourceError("idempotency_conflict", "This draft key was used for different input.", 409)
        return cls._view(connection, tenant, project, row)

    @staticmethod
    def _active(state):
        if state["status"] != "active":
            raise SourceError("project_archived", "Restore the project before changing an assignment draft.", 409)

    @classmethod
    def _append(cls, connection, tenant, project, actor, draft_id, context_id, revision,
                content, key, operation, digest, context, documentation_ids=None):
        if documentation_ids:
            row = connection.execute(
                """INSERT INTO curriculum_draft_revisions
                   (tenant_id,project_id,draft_id,revision,actor_user_id,content,documentation_ids)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, draft_id, revision, actor, Jsonb(content), Jsonb(list(map(str, documentation_ids)))),
            ).fetchone()
            for document_id in documentation_ids:
                connection.execute(
                    """INSERT INTO curriculum_draft_documents
                       (tenant_id,project_id,context_id,draft_id,revision,document_id)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (tenant, project, context_id, draft_id, revision, document_id),
                )
        else:
            row = connection.execute(
                """INSERT INTO curriculum_draft_revisions
                   (tenant_id,project_id,draft_id,revision,actor_user_id,content)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, draft_id, revision, actor, Jsonb(content)),
            ).fetchone()
        connection.execute(
            """INSERT INTO curriculum_draft_commands
               (tenant_id,project_id,idempotency_key,operation,request_sha256,draft_id,revision,actor_user_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (tenant, project, key, operation, digest, draft_id, revision, actor),
        )
        row["context_id"] = context_id
        return cls._view(connection, tenant, project, row, context=context)

    @staticmethod
    def _log(event, view):
        LOGGER.info(json.dumps({"event": event, "tenant_id": view.tenant_id,
                                "project_id": str(view.project_id), "draft_id": str(view.id),
                                "context_id": str(view.context_id), "revision": view.revision,
                                "objective_count": len(view.assignment.draft.objectives),
                                "requirement_count": len(view.assignment.draft.requirements),
                                "documentation_count": len(view.documentation_ids)}))

    def create(self, tenant: str, project: UUID, actor: UUID, context_id: UUID, body: DraftCreate) -> DraftRevisionView:
        body = self._body(DraftCreate, body)
        payload = self._payload(body.content)
        digest = self._hash("create", context_id, None, payload, body.documentation_ids)
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            replay = self._replay(connection, tenant, project, body.idempotency_key, digest)
            if replay is not None:
                return replay
            self._active(state)
            context = self._context(connection, tenant, project, context_id)
            documents = self._documents(connection, tenant, project, context, body.documentation_ids)
            self._bind(tenant, project, context, body.content, documents)
            draft_id = uuid4()
            connection.execute(
                """INSERT INTO curriculum_drafts
                   (tenant_id,project_id,id,context_id,actor_user_id,current_revision)
                   VALUES (%s,%s,%s,%s,%s,1)""",
                (tenant, project, draft_id, context_id, actor),
            )
            result = self._append(connection, tenant, project, actor, draft_id, context_id, 1,
                                  payload, body.idempotency_key, "create", digest, context, body.documentation_ids)
        self._log("curriculum_draft_created", result)
        return result

    def replace(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID,
                body: DraftReplace) -> DraftRevisionView:
        body = self._body(DraftReplace, body)
        payload = self._payload(body.content)
        digest = self._hash("replace", draft_id, body.expected_revision, payload, body.documentation_ids)
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            replay = self._replay(connection, tenant, project, body.idempotency_key, digest)
            if replay is not None:
                return replay
            self._active(state)
            row = connection.execute(
                "SELECT * FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (tenant, project, draft_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum draft not found")
            context = self._context(connection, tenant, project, row["context_id"])
            if row["current_revision"] != body.expected_revision:
                raise SourceError("draft_revision_conflict", "Read the latest assignment draft before editing it.", 409)
            documents = self._documents(connection, tenant, project, context, body.documentation_ids)
            # A direct delete of any historical document can remove this whole
            # draft even when the replacement drops that document. Lock/recheck
            # the head only after all new document fences, before revision FKs.
            current = connection.execute(
                "SELECT * FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR UPDATE",
                (tenant, project, draft_id),
            ).fetchone()
            if current is None:
                raise ProjectNotFoundError("curriculum draft not found")
            if (current["context_id"] != context.id
                    or current["current_revision"] != body.expected_revision):
                raise SourceError("draft_revision_conflict", "Read the latest assignment draft before editing it.", 409)
            self._bind(tenant, project, context, body.content, documents)
            revision = body.expected_revision + 1
            result = self._append(connection, tenant, project, actor, draft_id, row["context_id"], revision,
                                  payload, body.idempotency_key, "replace", digest, context, body.documentation_ids)
            connection.execute(
                """UPDATE curriculum_drafts SET current_revision=%s
                   WHERE tenant_id=%s AND project_id=%s AND id=%s""",
                (revision, tenant, project, draft_id),
            )
        self._log("curriculum_draft_revised", result)
        return result

    def read(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID,
             revision: int | None = None) -> DraftRevisionView:
        if revision is not None and (type(revision) is not int or not 1 <= revision <= 2_147_483_647):
            raise self._invalid()
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            row = connection.execute(
                """SELECT r.*,d.context_id FROM curriculum_drafts d
                   JOIN curriculum_draft_revisions r ON r.tenant_id=d.tenant_id
                     AND r.project_id=d.project_id AND r.draft_id=d.id
                     AND r.revision=coalesce(%s,d.current_revision)
                   WHERE d.tenant_id=%s AND d.project_id=%s AND d.id=%s""",
                (revision, tenant, project, draft_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum draft revision not found")
            return self._view(connection, tenant, project, row)

    def delete(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID) -> None:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=True)
            row = connection.execute(
                "DELETE FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING id",
                (tenant, project, draft_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFoundError("curriculum draft not found")
        LOGGER.info(json.dumps({"event": "curriculum_draft_deleted", "tenant_id": tenant,
                                "project_id": str(project), "draft_id": str(draft_id)}))
