"""Explicit review acceptance pins scoped immutable draft revisions, without inference."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

from pydantic import ValidationError

from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .drafts import DraftRepository
from .persistence import AssignmentActivate, AssignmentActivation
from .repository import ContextRepository


LOGGER = logging.getLogger("tutorial_workspace")


class AssignmentRepository:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _missing():
        return ProjectNotFoundError("assignment version not found")

    @staticmethod
    def _body(body):
        try:
            if not isinstance(body, AssignmentActivate):
                raise ValueError()
            # Revalidate raw in-memory field types before serialization can turn
            # a constructed boolean revision into an integer JSON value.
            return AssignmentActivate.model_validate(body, strict=True)
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise SourceError("invalid_assignment_activation", "Review the saved revision before activating it.", 422) from None

    @staticmethod
    def _hash(draft_id, body):
        value = {"operation": "activate", "target": str(draft_id),
                 "expected_revision": body.expected_revision, "consent": body.consent}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def _view(cls, connection, tenant, project, version):
        revision = connection.execute(
            """SELECT * FROM curriculum_draft_revisions
               WHERE tenant_id=%s AND project_id=%s AND draft_id=%s AND revision=%s""",
            (tenant, project, version["draft_id"], version["revision"]),
        ).fetchone()
        if revision is None:
            raise cls._missing()
        revision["context_id"] = version["context_id"]
        # This takes context/document fences before either head or version locks.
        # No current source-generation read can rewrite the accepted evidence.
        draft = DraftRepository._view(connection, tenant, project, revision)
        head = connection.execute(
            """SELECT id FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s
               AND context_id=%s AND id=%s FOR KEY SHARE""",
            (tenant, project, version["context_id"], version["draft_id"]),
        ).fetchone()
        retained = connection.execute(
            """SELECT id FROM curriculum_assignment_versions
               WHERE tenant_id=%s AND project_id=%s AND id=%s FOR KEY SHARE""",
            (tenant, project, version["id"]),
        ).fetchone()
        if head is None or retained is None:
            raise cls._missing()
        return AssignmentActivation(**version, draft=draft)

    def activate(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID,
                 body: AssignmentActivate) -> AssignmentActivation:
        body = self._body(body)
        digest = self._hash(draft_id, body)
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            command = connection.execute(
                """SELECT * FROM curriculum_draft_commands
                   WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s""",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if command is not None:
                if command["operation"] != "activate" or command["request_sha256"] != digest:
                    raise SourceError("idempotency_conflict", "This draft key was used for different input.", 409)
                version = connection.execute(
                    """SELECT * FROM curriculum_assignment_versions
                       WHERE tenant_id=%s AND project_id=%s AND id=%s""",
                    (tenant, project, command["assignment_version_id"]),
                ).fetchone()
                if version is None:
                    raise self._missing()
                result = self._view(connection, tenant, project, version)
                replayed = True
            else:
                DraftRepository._active(state)
                head = connection.execute(
                    "SELECT * FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                    (tenant, project, draft_id),
                ).fetchone()
                if head is None:
                    raise self._missing()
                context = DraftRepository._context(connection, tenant, project, head["context_id"])
                if head["current_revision"] != body.expected_revision:
                    raise SourceError("draft_revision_conflict", "Review the latest saved revision before activating it.", 409)
                revision = connection.execute(
                    """SELECT * FROM curriculum_draft_revisions
                       WHERE tenant_id=%s AND project_id=%s AND draft_id=%s AND revision=%s""",
                    (tenant, project, draft_id, body.expected_revision),
                ).fetchone()
                if revision is None:
                    raise self._missing()
                try:
                    selected = [UUID(str(value)) for value in revision["documentation_ids"]]
                    if len(set(selected)) != len(selected) or selected != sorted(selected, key=str):
                        raise ValueError()
                except (ValueError, TypeError, AttributeError):
                    raise DraftRepository._invalid() from None
                DraftRepository._documents(connection, tenant, project, context, selected)
                # Historical-document deletion can remove the entire draft even
                # when this revision no longer selects that document. Recheck the
                # head after document locks and before writing any revision FKs.
                current = connection.execute(
                    "SELECT * FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR UPDATE",
                    (tenant, project, draft_id),
                ).fetchone()
                if current is None:
                    raise self._missing()
                if current["context_id"] != context.id or current["current_revision"] != body.expected_revision:
                    raise SourceError("draft_revision_conflict", "Review the latest saved revision before activating it.", 409)
                revision["context_id"] = context.id
                DraftRepository._view(connection, tenant, project, revision, context=context)
                version = connection.execute(
                    """SELECT * FROM curriculum_assignment_versions
                       WHERE tenant_id=%s AND project_id=%s AND draft_id=%s AND revision=%s FOR KEY SHARE""",
                    (tenant, project, draft_id, body.expected_revision),
                ).fetchone()
                replayed = version is not None
                if version is None:
                    version = connection.execute(
                        """INSERT INTO curriculum_assignment_versions
                           (tenant_id,project_id,id,context_id,draft_id,revision,activated_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (tenant, project, uuid4(), context.id, draft_id, body.expected_revision, actor),
                    ).fetchone()
                connection.execute(
                    """INSERT INTO curriculum_draft_commands
                       (tenant_id,project_id,idempotency_key,operation,request_sha256,draft_id,revision,
                        actor_user_id,assignment_version_id)
                       VALUES (%s,%s,%s,'activate',%s,%s,%s,%s,%s)""",
                    (tenant, project, body.idempotency_key, digest, draft_id, body.expected_revision, actor, version["id"]),
                )
                result = self._view(connection, tenant, project, version)
        LOGGER.info(json.dumps({"event": "curriculum_assignment_activated", "tenant_id": tenant,
                                "project_id": str(project), "draft_id": str(draft_id),
                                "assignment_id": str(result.id), "revision": result.revision, "replayed": replayed}))
        return result

    def read(self, tenant: str, project: UUID, actor: UUID, assignment_id: UUID) -> AssignmentActivation:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            version = connection.execute(
                "SELECT * FROM curriculum_assignment_versions WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (tenant, project, assignment_id),
            ).fetchone()
            if version is None:
                raise self._missing()
            return self._view(connection, tenant, project, version)

    def latest(self, tenant: str, project: UUID, actor: UUID, draft_id: UUID) -> AssignmentActivation | None:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            head = connection.execute(
                "SELECT context_id FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (tenant, project, draft_id),
            ).fetchone()
            if head is None:
                raise self._missing()
            DraftRepository._context(connection, tenant, project, head["context_id"])
            version = connection.execute(
                """SELECT * FROM curriculum_assignment_versions
                   WHERE tenant_id=%s AND project_id=%s AND draft_id=%s ORDER BY revision DESC LIMIT 1""",
                (tenant, project, draft_id),
            ).fetchone()
            if version is not None:
                return self._view(connection, tenant, project, version)
            if connection.execute(
                "SELECT id FROM curriculum_drafts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR KEY SHARE",
                (tenant, project, draft_id),
            ).fetchone() is None:
                raise self._missing()
            return None
