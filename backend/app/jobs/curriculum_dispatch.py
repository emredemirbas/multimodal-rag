"""Independent durable outbox delivery and bounded curriculum lease recovery."""

import json
import logging
from uuid import uuid4

from ..curriculum.runs import RunRepository
from ..postgres import PostgresStore


LOGGER = logging.getLogger("tutorial_workspace.jobs")


def dispatch_once(store: PostgresStore, publish, *, limit: int = 20) -> int:
    token = uuid4()
    with store._connect() as connection:
        # Global enumeration selects only delivery identities. Every subsequent
        # mutation and broker message carries the complete persisted scope.
        rows = connection.execute(
            """WITH due AS (
                   SELECT tenant_id,project_id,id FROM curriculum_run_outbox
                   WHERE sent_at IS NULL AND available_at<=clock_timestamp()
                     AND (lease_expires_at IS NULL OR lease_expires_at<clock_timestamp())
                   ORDER BY available_at,tenant_id,project_id,id LIMIT %s FOR UPDATE SKIP LOCKED
               ) UPDATE curriculum_run_outbox o
               SET lease_token=%s,lease_expires_at=clock_timestamp()+interval '30 seconds'
               FROM due WHERE o.tenant_id=due.tenant_id AND o.project_id=due.project_id AND o.id=due.id
               RETURNING o.tenant_id,o.project_id,o.id,o.run_id""", (limit, token),
        ).fetchall()
    sent = 0
    for row in rows:
        try:
            publish(row["tenant_id"], row["project_id"], row["run_id"])
        except Exception:
            LOGGER.warning(json.dumps({"event": "curriculum_delivery_unavailable", "code": "broker_unavailable",
                                       "tenant_id": row["tenant_id"], "project_id": str(row["project_id"]),
                                       "run_id": str(row["run_id"])}))
            with store._connect() as connection:
                connection.execute(
                    """UPDATE curriculum_run_outbox SET lease_token=NULL,lease_expires_at=NULL,
                       publish_attempts=publish_attempts+1,available_at=clock_timestamp()+interval '5 seconds'
                       WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s""",
                    (row["tenant_id"], row["project_id"], row["id"], token),
                )
        else:
            with store._connect() as connection:
                # A very fast worker may already have checkpointed and reset
                # this row. Its new delivery must survive the old publish ACK.
                connection.execute(
                    """UPDATE curriculum_run_outbox SET sent_at=clock_timestamp(),lease_token=NULL,
                       lease_expires_at=NULL,publish_attempts=publish_attempts+1
                       WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s""",
                    (row["tenant_id"], row["project_id"], row["id"], token),
                )
            sent += 1
    return sent


def recover_expired(store: PostgresStore, *, limit: int = 20) -> int:
    with store._connect() as connection:
        rows = connection.execute(
            """SELECT tenant_id,project_id,id FROM curriculum_runs
               WHERE status='running' AND lease_expires_at<clock_timestamp()
               ORDER BY lease_expires_at,tenant_id,project_id,id LIMIT %s""", (limit,),
        ).fetchall()
    repository = RunRepository(store)
    # Discovery holds no run/outbox locks; the existing scoped lifecycle owns
    # authorization, project/context locks, fresh time and the bounded budget.
    return sum(repository.recover_expired(row["tenant_id"], row["project_id"], row["id"]) for row in rows)


def redeliver_unclaimed(store: PostgresStore, *, limit: int = 20) -> int:
    with store._connect() as connection:
        # No run lock after outbox lock: lifecycle takes run -> outbox. A run
        # claimed concurrently only produces a harmless duplicate delivery.
        rows = connection.execute(
            """WITH due AS (
                   SELECT o.tenant_id,o.project_id,o.id FROM curriculum_run_outbox o
                   JOIN curriculum_runs r ON r.tenant_id=o.tenant_id AND r.project_id=o.project_id AND r.id=o.run_id
                   WHERE r.status IN ('pending','retrying') AND r.available_at<=clock_timestamp()
                     AND o.sent_at<clock_timestamp()-interval '60 seconds'
                   ORDER BY o.sent_at,o.tenant_id,o.project_id,o.id LIMIT %s FOR UPDATE OF o SKIP LOCKED
               ) UPDATE curriculum_run_outbox o SET sent_at=NULL,available_at=clock_timestamp(),
                   lease_token=NULL,lease_expires_at=NULL
               FROM due WHERE o.tenant_id=due.tenant_id AND o.project_id=due.project_id AND o.id=due.id
               RETURNING o.id""", (limit,),
        ).fetchall()
    return len(rows)
