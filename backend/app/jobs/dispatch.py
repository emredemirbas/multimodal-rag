from uuid import uuid4

from ..sources.repository import SourceRepository
from ..artifacts.audio import record_audio_deleted


def dispatch_once(repository: SourceRepository, publish, *, limit: int = 20) -> int:
    token = uuid4()
    with repository.store._connect() as connection:
        rows = connection.execute(
            '''WITH due AS (
                   SELECT tenant_id,project_id,id FROM outbox_events
                   WHERE sent_at IS NULL AND available_at<=now()
                   AND (lease_expires_at IS NULL OR lease_expires_at<now())
                   ORDER BY available_at LIMIT %s FOR UPDATE SKIP LOCKED
               ) UPDATE outbox_events o SET lease_token=%s,lease_expires_at=now()+interval '30 seconds'
               FROM due WHERE o.tenant_id=due.tenant_id AND o.project_id=due.project_id AND o.id=due.id RETURNING o.*,
               (SELECT j.job_type FROM processing_jobs j WHERE j.tenant_id=o.tenant_id AND j.project_id=o.project_id AND j.id=o.job_id) AS job_type''',
            (limit, token),
        ).fetchall()
    sent = 0
    for row in rows:
        try:
            publish(row)
        except Exception:
            with repository.store._connect() as connection:
                connection.execute(
                    '''UPDATE outbox_events SET lease_token=NULL,lease_expires_at=NULL,
                       publish_attempts=publish_attempts+1,available_at=now()+interval '5 seconds'
                       WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s''',
                    (row['tenant_id'], row['project_id'], row['id'], token),
                )
        else:
            with repository.store._connect() as connection:
                connection.execute(
                    '''UPDATE outbox_events SET sent_at=now(),lease_token=NULL,lease_expires_at=NULL,publish_attempts=publish_attempts+1
                       WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s''',
                    (row['tenant_id'], row['project_id'], row['id'], token),
                )
            sent += 1
    return sent


def redeliver_unclaimed(repository: SourceRepository):
    with repository.store._connect() as connection:
        connection.execute(
            '''UPDATE outbox_events o SET sent_at=NULL,available_at=now()
               FROM processing_jobs j WHERE o.tenant_id=j.tenant_id AND o.project_id=j.project_id
               AND o.job_id=j.id AND j.status IN ('pending','retrying') AND j.available_at<=now()
               AND o.sent_at<now()-interval '60 seconds' '''
        )


def cleanup_once(repository: SourceRepository) -> int:
    token = uuid4()
    with repository.store._connect() as connection:
        row = connection.execute(
            '''WITH due AS (
                   SELECT id FROM artifact_cleanup WHERE available_at<=now()
                   AND (status='pending' OR (status='running' AND lease_expires_at<now()))
                   ORDER BY available_at LIMIT 1 FOR UPDATE SKIP LOCKED
               ) UPDATE artifact_cleanup c SET status='running',lease_token=%s,
               lease_expires_at=now()+interval '180 seconds',attempt_count=attempt_count+1
               FROM due WHERE c.id=due.id RETURNING c.*''', (token,),
        ).fetchone()
    if not row:
        return 0
    if row['attempt_count'] > 6:
        with repository.store._connect() as connection:
            connection.execute(
                "UPDATE artifact_cleanup SET status='failed',failure_code='cleanup_worker_lost',lease_token=NULL,lease_expires_at=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s",
                (row['tenant_id'], row['project_id'], row['id'], token),
            )
        return 0
    try:
        repository.artifacts.delete_prefix(row['object_prefix'])
    except Exception:
        with repository.store._connect() as connection:
            connection.execute(
                '''UPDATE artifact_cleanup SET status=%s,failure_code='storage_cleanup_unavailable',
                   available_at=now()+make_interval(secs=>%s),lease_token=NULL,lease_expires_at=NULL
                   WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s''',
                ('failed' if row['attempt_count'] >= 6 else 'pending', min(60, 2 ** row['attempt_count']),
                 row['tenant_id'], row['project_id'], row['id'], token),
            )
        return 0
    with repository.store._connect() as connection:
        completed = connection.execute(
            "UPDATE artifact_cleanup SET status='completed',failure_code=NULL,completed_at=now(),lease_token=NULL,lease_expires_at=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s AND lease_token=%s RETURNING id",
            (row['tenant_id'], row['project_id'], row['id'], token),
        ).fetchone()
        if completed:
            record_audio_deleted(connection, row)
    return 1
