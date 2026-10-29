"""Version editable draft content against immutable, authorized tutorial contexts."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..postgres import PostgresStore
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .contracts import AssignmentContent, AssignmentDraft
from .persistence import (
    MAX_DRAFT_STORAGE_BYTES,
    DraftCreate,
    DraftReplace,
    DraftRevisionView,
)
from .repository import ContextRepository
from .validation import CurriculumValidationError, bind_assignment


LOGGER = logging.getLogger("tutorial_workspace")


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
    def _hash(operation, target, expected_revision, payload):
        value = {"operation": operation, "target": str(target),
                 "expected_revision": expected_revision, "content": payload}
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
    def _bind(cls, tenant, project, context, content):
        try:
            draft = AssignmentDraft(tenant_id=tenant, project_id=project, **content.model_dump())
            # This slice has no trusted documentation capture/fetch boundary.
            return bind_assignment(context.request, draft, context.tutorial_snapshots, [])
        except (CurriculumValidationError, ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise cls._invalid() from None

    @classmethod
    def _view(cls, connection, tenant, project, row, *, context=None):
        if context is None:
            context = cls._context(connection, tenant, project, row["context_id"])
        try:
            content = AssignmentContent.model_validate_json(json.dumps(row["content"]))
            assignment = cls._bind(tenant, project, context, content)
            return DraftRevisionView(
                id=row["draft_id"], tenant_id=tenant, project_id=project,
                context_id=row["context_id"], revision=row["revision"],
                created_at=row["created_at"], assignment=assignment,
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
                content, key, operation, digest, context):
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
                                "requirement_count": len(view.assignment.draft.requirements)}))

    def create(self, tenant: str, project: UUID, actor: UUID, context_id: UUID, body: DraftCreate) -> DraftRevisionView:
        body = self._body(DraftCreate, body)
        payload = self._payload(body.content)
        digest = self._hash("create", context_id, None, payload)
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            replay = self._replay(connection, tenant, project, body.idempotency_key, digest)
            if replay is not None:
                return replay
            self._active(state)
            context = self._context(connection, tenant, project, context_id)
            self._bind(tenant, project, context, body.content)
            draft_id = uuid4()
            connection.execute(
                """INSERT INTO curriculum_drafts
                   (tenant_id,project_id,id,context_id,actor_user_id,current_revision)
                   VALUES (%s,%s,%s,%s,%s,1)""",
                (tenant, project, draft_id, context_id, actor),
            )
            result = self._append(connection, tenant, project, actor, draft_id, context_id, 1,
                                  payload, body.idempotency_key, "create", digest, context)
        self._log("curriculum_draft_created", result)
        return result

    def replace(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID,
                body: DraftReplace) -> DraftRevisionView:
        body = self._body(DraftReplace, body)
        payload = self._payload(body.content)
        digest = self._hash("replace", draft_id, body.expected_revision, payload)
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
            self._bind(tenant, project, context, body.content)
            revision = body.expected_revision + 1
            result = self._append(connection, tenant, project, actor, draft_id, row["context_id"], revision,
                                  payload, body.idempotency_key, "replace", digest, context)
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
