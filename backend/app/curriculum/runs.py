"""Internal durable curriculum lifecycle; no broker, provider or public producer."""

import hashlib
import json
import logging
from typing import get_args
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..postgres import PostgresStore
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .repository import ContextRepository
from .run_contracts import (
    LEASE_SECONDS, MAX_FAILURES, RETRY_DELAY_SECONDS, FailureCode, RunClaim, RunCommand, RunCreate, RunView,
)


LOGGER = logging.getLogger("tutorial_workspace")


class RunRepository:
    def __init__(self, store: PostgresStore):
        self.store = store

    @staticmethod
    def _invalid():
        return SourceError("invalid_curriculum_run", "The curriculum run could not be validated.", 422)

    @classmethod
    def _body(cls, contract, body):
        try:
            if not isinstance(body, contract):
                raise ValueError()
            # JSON serialization of a mutated int field can turn True into 1.
            # Keep Python values intact while rebuilding this internal boundary.
            return contract.model_validate(body.model_dump(warnings=False), strict=True)
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
            raise cls._invalid() from None

    @staticmethod
    def _view(row):
        return RunView.model_validate({name: row[name] for name in RunView.model_fields if name in row})

    @staticmethod
    def _digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _row(connection, tenant, project, run_id, *, lock=False):
        row = connection.execute(
            """SELECT r.*,
                      (SELECT draft_id FROM curriculum_run_results z WHERE z.tenant_id=r.tenant_id
                       AND z.project_id=r.project_id AND z.run_id=r.id) AS result_draft_id,
                      (SELECT revision FROM curriculum_run_results z WHERE z.tenant_id=r.tenant_id
                       AND z.project_id=r.project_id AND z.run_id=r.id) AS result_revision
               FROM curriculum_runs r WHERE tenant_id=%s AND project_id=%s AND id=%s"""
            + (" FOR UPDATE OF r" if lock else ""), (tenant, project, run_id),
        ).fetchone()
        if row is None:
            raise ProjectNotFoundError("curriculum run not found")
        return row

    @staticmethod
    def _context(connection, tenant, project, context_id):
        # A direct source DELETE already owns its source row when its cleanup
        # trigger reaches this context. Never acquire a source lock after this.
        return connection.execute(
            "SELECT id FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s FOR KEY SHARE",
            (tenant, project, context_id),
        ).fetchone()

    @staticmethod
    def _log(event, row):
        LOGGER.info(json.dumps({"event": event, "tenant_id": row["tenant_id"],
                                "project_id": str(row["project_id"]), "run_id": str(row["id"]),
                                "status": row["status"], "attempt_count": row["attempt_count"],
                                "failure_count": row["failure_count"], "checkpoint_seq": row["checkpoint_seq"]}))

    @staticmethod
    def _enqueue(connection, row):
        connection.execute(
            """INSERT INTO curriculum_run_outbox (tenant_id,project_id,id,run_id,available_at)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,project_id,run_id)
               DO UPDATE SET available_at=EXCLUDED.available_at,sent_at=NULL,lease_token=NULL,lease_expires_at=NULL""",
            (row["tenant_id"], row["project_id"], uuid4(), row["id"], row["available_at"]),
        )

    @staticmethod
    def _close_attempt(connection, row, code, *, cancelled=False):
        scope = (row["tenant_id"], row["project_id"], row["id"], row["attempt_count"])
        connection.execute(
            """UPDATE curriculum_run_attempts SET status=%s,failure_code=%s,finished_at=clock_timestamp()
               WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND attempt_number=%s AND status='running'""",
            ("cancelled" if cancelled else "failed", code, *scope),
        )
        # Started calls have no accepted result. Do not invent zero token counts
        # or a model duration for work whose completion was never committed.
        connection.execute(
            """UPDATE curriculum_model_calls SET status='interrupted',failure_code=%s,finished_at=clock_timestamp()
               WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND attempt_number=%s AND status='started'""",
            (code, *scope),
        )

    @classmethod
    def _terminal(cls, connection, row, code, *, cancelled=False):
        cls._close_attempt(connection, row, code, cancelled=cancelled)
        result = connection.execute(
            """UPDATE curriculum_runs SET status=%s,failure_code=%s,lease_token=NULL,lease_expires_at=NULL,
               finished_at=clock_timestamp(),updated_at=clock_timestamp()
               WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING *""",
            ("cancelled" if cancelled else "failed", code, row["tenant_id"], row["project_id"], row["id"]),
        ).fetchone()
        connection.execute("DELETE FROM curriculum_run_outbox WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
                           (row["tenant_id"], row["project_id"], row["id"]))
        return result

    @classmethod
    def _failed(cls, connection, row, code, *, retryable):
        failures = min(MAX_FAILURES, row["failure_count"] + 1)
        connection.execute(
            "UPDATE curriculum_runs SET failure_count=%s WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (failures, row["tenant_id"], row["project_id"], row["id"]),
        )
        if not retryable or failures >= MAX_FAILURES:
            return cls._terminal(connection, row, code)
        cls._close_attempt(connection, row, code)
        result = connection.execute(
            """UPDATE curriculum_runs SET status='retrying',failure_code=%s,lease_token=NULL,lease_expires_at=NULL,
               available_at=clock_timestamp()+make_interval(secs=>%s),updated_at=clock_timestamp(),finished_at=NULL
               WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING *""",
            (code, RETRY_DELAY_SECONDS, row["tenant_id"], row["project_id"], row["id"]),
        ).fetchone()
        cls._enqueue(connection, result)
        return result

    def _worker_row(self, connection, tenant, project, run_id):
        # The initial unlocked lookup supplies immutable actor/context identities.
        # Locks then follow the same membership -> project -> context -> run order
        # as user commands and never trust actor metadata supplied by a delivery.
        initial = connection.execute(
            "SELECT actor_user_id,context_id FROM curriculum_runs WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (tenant, project, run_id),
        ).fetchone()
        if initial is None:
            return None, None
        member = connection.execute(
            "SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE",
            (tenant, initial["actor_user_id"]),
        ).fetchone()
        state = connection.execute(
            "SELECT status FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL FOR UPDATE",
            (tenant, project),
        ).fetchone()
        if state is None or self._context(connection, tenant, project, initial["context_id"]) is None:
            return None, None
        try:
            row = self._row(connection, tenant, project, run_id, lock=True)
        except ProjectNotFoundError:
            return None, None
        if row["actor_user_id"] != initial["actor_user_id"] or row["context_id"] != initial["context_id"]:
            return None, None
        return row, ("authorization_revoked" if member is None else
                     "project_archived" if state["status"] != "active" else None)

    def _lease(self, connection, claim):
        try:
            claim = self._body(RunClaim, claim)
        except SourceError:
            return None
        row, blocked = self._worker_row(connection, claim.tenant_id, claim.project_id, claim.run_id)
        if (row is None or row["status"] != "running" or row["lease_token"] != claim.lease_token
                or row["attempt_count"] != claim.attempt_number):
            return None
        if blocked is not None:
            self._terminal(connection, row, blocked)
            return None
        # PostgreSQL now() denotes transaction start and can become stale while
        # waiting for row locks. Evaluate wall time only after every fence lock.
        live = connection.execute("SELECT %s::timestamptz>clock_timestamp() AS live",
                                  (row["lease_expires_at"],)).fetchone()["live"]
        return row if live else None

    def create(self, tenant: str, project: UUID, actor: UUID, context_id: UUID, body: RunCreate) -> RunView:
        body = self._body(RunCreate, body)
        digest = self._digest({"tenant_id": tenant, "project_id": str(project),
                               "context_id": str(context_id), "workflow_version": body.workflow_version})
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            existing = connection.execute(
                "SELECT * FROM curriculum_runs WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != digest:
                    raise SourceError("idempotency_conflict", "This run key was used for different input.", 409)
                return self._view(self._row(connection, tenant, project, existing["id"]))
            if state["status"] != "active":
                raise SourceError("project_archived", "Restore the project before creating a curriculum run.", 409)
            if self._context(connection, tenant, project, context_id) is None:
                raise ProjectNotFoundError("curriculum context not found")
            row = connection.execute(
                """INSERT INTO curriculum_runs
                   (tenant_id,project_id,id,context_id,actor_user_id,idempotency_key,request_sha256,workflow_version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, uuid4(), context_id, actor, body.idempotency_key, digest, body.workflow_version),
            ).fetchone()
            self._enqueue(connection, row)
            result = self._view(row)
        self._log("curriculum_run_created", row)
        return result

    def read(self, tenant: str, project: UUID, actor: UUID, run_id: UUID) -> RunView:
        with self.store._connect() as connection:
            ContextRepository._scope(connection, tenant, project, actor, write=False)
            return self._view(self._row(connection, tenant, project, run_id))

    def _command(self, tenant, project, actor, run_id, body, operation):
        body = self._body(RunCommand, body)
        digest = self._digest({"operation": operation, "run_id": str(run_id)})
        with self.store._connect() as connection:
            state = ContextRepository._scope(connection, tenant, project, actor, write=True)
            initial = self._row(connection, tenant, project, run_id)
            if operation == "retry" and initial["actor_user_id"] != actor:
                raise ProjectNotFoundError("curriculum run not found")
            if self._context(connection, tenant, project, initial["context_id"]) is None:
                raise ProjectNotFoundError("curriculum context not found")
            row = self._row(connection, tenant, project, run_id, lock=True)
            receipt = connection.execute(
                """SELECT request_sha256,response FROM curriculum_run_commands
                   WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND idempotency_key=%s""",
                (tenant, project, run_id, body.idempotency_key),
            ).fetchone()
            if receipt is not None:
                if receipt["request_sha256"] != digest:
                    raise SourceError("idempotency_conflict", "This command key was used for a different action.", 409)
                return RunView.model_validate_json(json.dumps(receipt["response"]))
            if operation == "cancel":
                if row["status"] not in {"pending", "running", "retrying"}:
                    raise SourceError("curriculum_run_state_conflict", "Only a pending or running curriculum run can be cancelled.", 409)
                row = self._terminal(connection, row, "cancelled", cancelled=True)
            else:
                if state["status"] != "active":
                    raise SourceError("project_archived", "Restore the project before retrying a curriculum run.", 409)
                if row["status"] not in {"failed", "cancelled"}:
                    raise SourceError("curriculum_run_state_conflict", "Only a failed or cancelled curriculum run can be retried.", 409)
                row = connection.execute(
                    """UPDATE curriculum_runs SET status='pending',failure_count=0,failure_code=NULL,
                       available_at=clock_timestamp(),updated_at=clock_timestamp(),finished_at=NULL,
                       lease_token=NULL,lease_expires_at=NULL
                       WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING *""",
                    (tenant, project, run_id),
                ).fetchone()
                self._enqueue(connection, row)
            result = self._view(row)
            connection.execute(
                """INSERT INTO curriculum_run_commands
                   (tenant_id,project_id,run_id,idempotency_key,operation,request_sha256,actor_user_id,response)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (tenant, project, run_id, body.idempotency_key, operation, digest, actor,
                 Jsonb(result.model_dump(mode="json"))),
            )
        self._log("curriculum_run_" + operation, row)
        return result

    def cancel(self, tenant: str, project: UUID, actor: UUID, run_id: UUID, body: RunCommand) -> RunView:
        return self._command(tenant, project, actor, run_id, body, "cancel")

    def retry(self, tenant: str, project: UUID, actor: UUID, run_id: UUID, body: RunCommand) -> RunView:
        return self._command(tenant, project, actor, run_id, body, "retry")

    def claim(self, tenant: str, project: UUID, run_id: UUID) -> RunClaim | None:
        with self.store._connect() as connection:
            row, blocked = self._worker_row(connection, tenant, project, run_id)
            if row is None or row["status"] not in {"pending", "retrying"}:
                return None
            if blocked is not None:
                self._terminal(connection, row, blocked)
                return None
            due = connection.execute("SELECT %s::timestamptz<=clock_timestamp() AS due",
                                     (row["available_at"],)).fetchone()["due"]
            if not due:
                return None
            token = uuid4()
            row = connection.execute(
                """UPDATE curriculum_runs SET status='running',attempt_count=attempt_count+1,
                   lease_token=%s,lease_expires_at=clock_timestamp()+make_interval(secs=>%s),
                   updated_at=clock_timestamp(),finished_at=NULL,failure_code=NULL
                   WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING *""",
                (token, LEASE_SECONDS, tenant, project, run_id),
            ).fetchone()
            connection.execute(
                """INSERT INTO curriculum_run_attempts (tenant_id,project_id,run_id,attempt_number,lease_token)
                   VALUES (%s,%s,%s,%s,%s)""", (tenant, project, run_id, row["attempt_count"], token),
            )
            result = RunClaim(tenant_id=tenant, project_id=project, run_id=run_id,
                              lease_token=token, attempt_number=row["attempt_count"])
        self._log("curriculum_run_claimed", row)
        return result

    def heartbeat(self, claim: RunClaim) -> bool:
        with self.store._connect() as connection:
            row = self._lease(connection, claim)
            if row is None:
                return False
            connection.execute(
                """UPDATE curriculum_runs SET lease_expires_at=clock_timestamp()+make_interval(secs=>%s),
                   updated_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s AND id=%s""",
                (LEASE_SECONDS, row["tenant_id"], row["project_id"], row["id"]),
            )
        return True

    def fail(self, claim: RunClaim, code: FailureCode, *, retryable: bool) -> bool:
        if code not in get_args(FailureCode) or type(retryable) is not bool:
            raise self._invalid()
        with self.store._connect() as connection:
            row = self._lease(connection, claim)
            if row is None:
                return False
            row = self._failed(connection, row, code,
                               retryable=retryable and code not in {"authorization_revoked", "project_archived", "cancelled"})
        self._log("curriculum_run_failed", row)
        return True

    def recover_expired(self, tenant: str, project: UUID, run_id: UUID) -> bool:
        with self.store._connect() as connection:
            row, blocked = self._worker_row(connection, tenant, project, run_id)
            if row is None or row["status"] != "running":
                return False
            expired = connection.execute("SELECT %s::timestamptz<=clock_timestamp() AS expired",
                                         (row["lease_expires_at"],)).fetchone()["expired"]
            if not expired:
                return False
            row = (self._terminal(connection, row, blocked) if blocked is not None else
                   self._failed(connection, row, "worker_lost", retryable=True))
        self._log("curriculum_run_recovered", row)
        return True
