"""Private leased checkpoints and local-call attribution, without inference."""

import hashlib
import json
import logging

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..sources.contracts import SourceError
from .run_contracts import (
    MAX_CALLS_PER_RUN,
    MAX_CHECKPOINT_BYTES,
    MAX_CHECKPOINT_STORAGE_BYTES,
    CheckpointSave,
    CheckpointView,
    ModelCallFinish,
    ModelCallStart,
    ModelCallView,
    RunClaim,
)
from .runs import RunRepository


LOGGER = logging.getLogger("tutorial_workspace")


class RunProgressRepository(RunRepository):
    @staticmethod
    def _call_live_at_finish(connection, run):
        return connection.execute("SELECT %s::timestamptz>clock_timestamp() AS live",
                                  (run["lease_expires_at"],)).fetchone()["live"]

    @staticmethod
    def _progress_invalid():
        return SourceError("invalid_curriculum_progress", "The run progress could not be validated.", 422)

    @classmethod
    def _checked(cls, contract, value):
        try:
            if not isinstance(value, contract):
                raise ValueError()
            return contract.model_validate(value.model_dump(warnings=False), strict=True)
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise cls._progress_invalid() from None

    @classmethod
    def _json(cls, payload):
        def compatible(value):
            if isinstance(value, str):
                return "\x00" not in value
            if isinstance(value, list):
                return all(compatible(item) for item in value)
            if isinstance(value, dict):
                return all(compatible(key) and compatible(item) for key, item in value.items())
            return True

        try:
            if not compatible(payload):
                raise ValueError()
            compact = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
            spaced = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            return compact, spaced
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise cls._progress_invalid() from None

    @staticmethod
    def _scope(claim):
        return claim.tenant_id, claim.project_id, claim.run_id

    @staticmethod
    def _conflict(code):
        return SourceError(code, "The run progress key was used for different input or order.", 409)

    @staticmethod
    def _call_view(row):
        # PostgreSQL NUMERIC is Decimal; the constraint guarantees local spend 0.
        return ModelCallView(**{key: row[key] for key in ModelCallView.model_fields if key != "billed_usd"},
                             billed_usd=0)

    def _save_checkpoint(self, connection, run, claim, body, *, new_only=False):
        """Append inside the caller's already fenced transaction."""
        compact, spaced = self._json(body.payload)
        if len(compact) > MAX_CHECKPOINT_BYTES or len(spaced) > MAX_CHECKPOINT_STORAGE_BYTES:
            raise self._progress_invalid()
        scope = self._scope(claim)
        if new_only and body.sequence != run["checkpoint_seq"] + 1:
            raise self._conflict("checkpoint_sequence_conflict")
        # JSONB expands exponents and normalizes negative zero/large floats.
        # Bound its actual representation before INSERT or transferring an
        # expanded payload, then hash the values a later load will return.
        normalized = connection.execute(
            """SELECT octet_length(value::text) AS byte_count,
                      CASE WHEN octet_length(value::text)<=%s THEN value ELSE NULL END AS payload
               FROM (SELECT %s::jsonb AS value) AS checkpoint""",
            (MAX_CHECKPOINT_STORAGE_BYTES, Jsonb(body.payload)),
        ).fetchone()
        if normalized["byte_count"] > MAX_CHECKPOINT_STORAGE_BYTES:
            raise self._progress_invalid()
        payload = normalized["payload"]
        compact, spaced = self._json(payload)
        if len(compact) > MAX_CHECKPOINT_BYTES or len(spaced) > MAX_CHECKPOINT_STORAGE_BYTES:
            raise self._progress_invalid()
        digest = hashlib.sha256(compact).hexdigest()
        previous = connection.execute(
            """SELECT stage,content_sha256 FROM curriculum_run_checkpoints
               WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND sequence=%s""",
            (*scope, body.sequence),
        ).fetchone()
        if previous:
            if previous["stage"] != body.stage or previous["content_sha256"] != digest:
                raise self._conflict("checkpoint_conflict")
            return
        if body.sequence != run["checkpoint_seq"] + 1:
            raise self._conflict("checkpoint_sequence_conflict")
        connection.execute(
            """INSERT INTO curriculum_run_checkpoints
               (tenant_id,project_id,run_id,sequence,attempt_number,stage,workflow_version,payload,content_sha256)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (*scope, body.sequence, claim.attempt_number, body.stage, run["workflow_version"], Jsonb(payload), digest),
        )
        connection.execute(
            """UPDATE curriculum_runs SET checkpoint_seq=%s,updated_at=clock_timestamp()
               WHERE tenant_id=%s AND project_id=%s AND id=%s""", (body.sequence, *scope),
        )

    def save_checkpoint(self, claim: RunClaim, body: CheckpointSave) -> bool:
        body = self._checked(CheckpointSave, body)
        with self.store._connect() as connection:
            run = self._lease(connection, claim)
            if run is None:
                return False
            self._save_checkpoint(connection, run, claim, body)
        LOGGER.info(json.dumps({"event": "curriculum_checkpoint_saved", "tenant_id": claim.tenant_id,
                                "project_id": str(claim.project_id), "run_id": str(claim.run_id),
                                "sequence": body.sequence, "stage": body.stage}))
        return True

    def load_checkpoints(self, claim: RunClaim) -> list[CheckpointView] | None:
        with self.store._connect() as connection:
            if self._lease(connection, claim) is None:
                return None
            rows = connection.execute(
                """SELECT * FROM curriculum_run_checkpoints
                   WHERE tenant_id=%s AND project_id=%s AND run_id=%s ORDER BY sequence""", self._scope(claim),
            ).fetchall()
            return [CheckpointView(**{key: row[key] for key in CheckpointView.model_fields}) for row in rows]

    def begin_call(self, claim: RunClaim, body: ModelCallStart) -> ModelCallView | None:
        body = self._checked(ModelCallStart, body)
        # Preserve replay of accepted pre-0024 receipts: their hash did not
        # contain these newly optional NULL metadata fields.
        metadata = body.model_dump(mode="json")
        if body.input_sha256 is None:
            for key in ("input_sha256", "schema_version", "request_version"):
                metadata.pop(key)
        digest = hashlib.sha256(self._json(metadata)[0]).hexdigest()
        with self.store._connect() as connection:
            run = self._lease(connection, claim)
            if run is None:
                return None
            scope = self._scope(claim)
            previous = connection.execute(
                "SELECT * FROM curriculum_model_calls WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND call_id=%s",
                (*scope, body.call_id),
            ).fetchone()
            if previous:
                if previous["request_sha256"] != digest or previous["attempt_number"] != claim.attempt_number:
                    raise self._conflict("model_call_conflict")
                return self._call_view(previous)
            count = connection.execute(
                "SELECT count(*) AS count FROM curriculum_model_calls WHERE tenant_id=%s AND project_id=%s AND run_id=%s",
                scope,
            ).fetchone()["count"]
            if count >= MAX_CALLS_PER_RUN:
                raise self._progress_invalid()
            row = connection.execute(
                """INSERT INTO curriculum_model_calls
                   (tenant_id,project_id,run_id,call_id,attempt_number,purpose,provider,model,model_digest,
                    engine,prompt_version,input_characters,input_tokens,request_sha256,
                    input_sha256,schema_version,request_version,status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'started') RETURNING *""",
                (*scope, body.call_id, claim.attempt_number, body.purpose, body.provider, body.model,
                 body.model_digest, body.engine, body.prompt_version, body.input_characters, body.input_tokens, digest,
                 body.input_sha256, body.schema_version, body.request_version),
            ).fetchone()
            if not self._call_live_at_finish(connection, run):
                connection.rollback()
                return None
            result = self._call_view(row)
        LOGGER.info(json.dumps({"event": "curriculum_call_started", "tenant_id": claim.tenant_id,
                                "project_id": str(claim.project_id), "run_id": str(claim.run_id),
                                "call_id": str(body.call_id), "attempt_number": claim.attempt_number}))
        return result

    def finish_call(self, claim: RunClaim, body: ModelCallFinish) -> bool:
        body = self._checked(ModelCallFinish, body)
        with self.store._connect() as connection:
            run = self._lease(connection, claim)
            if run is None:
                return False
            scope = self._scope(claim)
            previous = connection.execute(
                """SELECT * FROM curriculum_model_calls
                   WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND call_id=%s AND attempt_number=%s""",
                (*scope, body.call_id, claim.attempt_number),
            ).fetchone()
            if previous is None:
                return False
            if previous["status"] != "started":
                if any(previous[key] != value for key, value in body.model_dump().items()):
                    raise self._conflict("model_call_conflict")
                return True
            connection.execute(
                """UPDATE curriculum_model_calls
                   SET status=%s,input_tokens=%s,output_tokens=%s,output_characters=%s,duration_ms=%s,
                       failure_code=%s,finished_at=clock_timestamp()
                   WHERE tenant_id=%s AND project_id=%s AND run_id=%s AND call_id=%s AND attempt_number=%s""",
                (body.status, body.input_tokens, body.output_tokens, body.output_characters,
                 body.duration_ms, body.failure_code, *scope, body.call_id, claim.attempt_number),
            )
            if not self._call_live_at_finish(connection, run):
                connection.rollback()
                return False
        LOGGER.info(json.dumps({"event": "curriculum_call_finished", "tenant_id": claim.tenant_id,
                                "project_id": str(claim.project_id), "run_id": str(claim.run_id),
                                "call_id": str(body.call_id), "outcome": body.status, "duration_ms": body.duration_ms}))
        return True
