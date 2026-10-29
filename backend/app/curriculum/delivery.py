"""Fenced delivery inputs, checkpoint continuation and atomic draft publication."""

import json
import logging
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from ..sources.contracts import SourceError
from .contracts import AssignmentContent
from .drafts import DraftRepository
from .persistence import ContextView, DraftRevisionView
from .repository import ContextRepository
from .run_contracts import CheckpointSave, CheckpointView, RunClaim, RunView
from .run_progress import RunProgressRepository


LOGGER = logging.getLogger("tutorial_workspace")


class _DeliveryLeaseExpired(Exception):
    pass


class RunDeliveryRepository(RunProgressRepository):
    @staticmethod
    def _live_at_finish(connection, run):
        # Outbox writes can also wait on a concurrent dispatcher. Recheck the
        # original deadline after every write, rolling back all accepted output
        # if time elapsed after the run's status/lease columns were changed.
        if not connection.execute("SELECT %s::timestamptz>clock_timestamp() AS live",
                                  (run["lease_expires_at"],)).fetchone()["live"]:
            raise _DeliveryLeaseExpired()

    @staticmethod
    def _no_open_calls(connection, claim):
        open_call = connection.execute(
            """SELECT 1 FROM curriculum_model_calls
               WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND status='started' LIMIT 1""",
            (claim.tenant_id, claim.project_id, claim.run_id),
        ).fetchone()
        if open_call:
            raise SourceError("curriculum_calls_incomplete", "Finish call attribution before accepting stage output.", 409)

    @staticmethod
    def _finish_attempt(connection, claim, status):
        connection.execute(
            """UPDATE curriculum_run_attempts SET status=%s,failure_code=NULL,finished_at=clock_timestamp()
               WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND attempt_number=%s AND status='running'""",
            (status, claim.tenant_id, claim.project_id, claim.run_id, claim.attempt_number),
        )

    def load_input(self, claim: RunClaim) -> tuple[RunView, ContextView, list[CheckpointView]] | None:
        with self.store._connect() as connection:
            run = self._lease(connection, claim)
            if run is None:
                return None
            row = connection.execute(
                """SELECT * FROM curriculum_contexts WHERE tenant_id=%s AND project_id=%s AND id=%s""",
                (claim.tenant_id, claim.project_id, run["context_id"]),
            ).fetchone()
            checkpoints = connection.execute(
                """SELECT * FROM curriculum_run_checkpoints
                   WHERE tenant_id=%s AND project_id=%s AND run_id=%s ORDER BY sequence""",
                self._scope(claim),
            ).fetchall()
            return (self._view(run), ContextRepository._view(row),
                    [CheckpointView(**{key: item[key] for key in CheckpointView.model_fields}) for item in checkpoints])

    def continue_with_checkpoint(self, claim: RunClaim, body: CheckpointSave) -> bool:
        body = self._checked(CheckpointSave, body)
        try:
            with self.store._connect() as connection:
                run = self._lease(connection, claim)
                if run is None:
                    return False
                self._no_open_calls(connection, claim)
                self._save_checkpoint(connection, run, claim, body, new_only=True)
                self._finish_attempt(connection, claim, "checkpointed")
                row = connection.execute(
                    """UPDATE curriculum_runs SET status='pending',failure_code=NULL,
                       lease_token=NULL,lease_expires_at=NULL,available_at=clock_timestamp(),
                       updated_at=clock_timestamp(),finished_at=NULL
                       WHERE tenant_id=%s AND project_id=%s AND id=%s
                       AND lease_expires_at>clock_timestamp() RETURNING *""",
                    self._scope(claim),
                ).fetchone()
                if row is None:
                    raise _DeliveryLeaseExpired()
                self._enqueue(connection, row)
                self._live_at_finish(connection, run)
        except _DeliveryLeaseExpired:
            return False
        self._log("curriculum_run_continued", row)
        return True

    def publish_draft(self, claim: RunClaim, content: AssignmentContent) -> DraftRevisionView | None:
        # Rebuild Python values, preserving strict bool/int/UUID boundaries even
        # if an internal caller mutated or constructed the model unchecked.
        try:
            if not isinstance(content, AssignmentContent):
                raise ValueError()

            def known_fields(value):
                if isinstance(value, BaseModel):
                    if set(value.__dict__) - set(type(value).model_fields) or value.__pydantic_extra__:
                        raise ValueError()
                    for nested in value.__dict__.values():
                        known_fields(nested)
                elif isinstance(value, dict):
                    for nested in value.values():
                        known_fields(nested)
                elif isinstance(value, list):
                    for nested in value:
                        known_fields(nested)

            known_fields(content)
            content = AssignmentContent.model_validate(content.model_dump(warnings=False), strict=True)
        except (ValueError, TypeError, AttributeError, RecursionError):
            raise DraftRepository._invalid() from None
        payload = DraftRepository._payload(content)
        try:
            with self.store._connect() as connection:
                run = self._lease(connection, claim)
                if run is None:
                    return None
                self._no_open_calls(connection, claim)
                context = DraftRepository._context(connection, claim.tenant_id, claim.project_id, run["context_id"])
                DraftRepository._bind(claim.tenant_id, claim.project_id, context, content)
                draft_id = uuid4()
                connection.execute(
                    """INSERT INTO curriculum_drafts
                       (tenant_id,project_id,id,context_id,actor_user_id,current_revision)
                       VALUES (%s,%s,%s,%s,%s,1)""",
                    (claim.tenant_id, claim.project_id, draft_id, run["context_id"], run["actor_user_id"]),
                )
                row = connection.execute(
                    """INSERT INTO curriculum_draft_revisions
                       (tenant_id,project_id,draft_id,revision,actor_user_id,content)
                       VALUES (%s,%s,%s,1,%s,%s) RETURNING *""",
                    (claim.tenant_id, claim.project_id, draft_id, run["actor_user_id"], Jsonb(payload)),
                ).fetchone()
                connection.execute(
                    """INSERT INTO curriculum_run_results (tenant_id,project_id,run_id,draft_id,revision)
                       VALUES (%s,%s,%s,%s,1)""", (*self._scope(claim), draft_id),
                )
                row["context_id"] = run["context_id"]
                result = DraftRepository._view(connection, claim.tenant_id, claim.project_id, row, context=context)
                self._finish_attempt(connection, claim, "succeeded")
                completed = connection.execute(
                    """UPDATE curriculum_runs SET status='succeeded',failure_code=NULL,
                       lease_token=NULL,lease_expires_at=NULL,finished_at=clock_timestamp(),updated_at=clock_timestamp()
                       WHERE tenant_id=%s AND project_id=%s AND id=%s
                       AND lease_expires_at>clock_timestamp() RETURNING *""",
                    self._scope(claim),
                ).fetchone()
                if completed is None:
                    raise _DeliveryLeaseExpired()
                connection.execute(
                    "DELETE FROM curriculum_run_outbox WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
                    self._scope(claim),
                )
                self._live_at_finish(connection, run)
        except _DeliveryLeaseExpired:
            return None
        self._log("curriculum_run_succeeded", completed)
        LOGGER.info(json.dumps({"event": "curriculum_run_draft_published", "tenant_id": claim.tenant_id,
                                "project_id": str(claim.project_id), "run_id": str(claim.run_id),
                                "draft_id": str(result.id), "revision": result.revision}))
        return result
