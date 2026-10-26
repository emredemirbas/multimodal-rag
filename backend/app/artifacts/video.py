"""Terminal raw-video retirement; caller holds the scoped project lock."""
from uuid import UUID, uuid4

from .storage import object_prefix


def video_prefix(tenant: str, project: UUID, source: UUID, generation: int) -> str:
    return f'{object_prefix(tenant, project, source)}video/{generation}/'


def retire_video(connection, tenant, project, source, job=None) -> int:
    rows = connection.execute(
        '''SELECT * FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
           AND (%s::uuid IS NULL OR job_id=%s::uuid) AND cleanup_id IS NULL FOR UPDATE''',
        (tenant, project, source, job, job),
    ).fetchall()
    for row in rows:
        cleanup = uuid4()
        connection.execute(
            '''INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix)
               VALUES (%s,%s,%s,%s,%s)''',
            (cleanup, tenant, project, row['actor_user_id'], video_prefix(tenant, project, source, row['generation'])),
        )
        connection.execute('UPDATE video_inputs SET cleanup_id=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s',
                           (cleanup, tenant, project, source, row['job_id']))
        connection.execute(
            '''UPDATE sources SET metadata=jsonb_set(metadata,'{video_cleanup_id}',to_jsonb(%s::text)),updated_at=now()
               WHERE tenant_id=%s AND project_id=%s AND id=%s''', (str(cleanup), tenant, project, source),
        )
    return len(rows)


def record_video_deleted(connection, cleanup):
    connection.execute(
        '''UPDATE video_inputs SET deleted_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s
           AND cleanup_id=%s AND deleted_at IS NULL''', (cleanup['tenant_id'], cleanup['project_id'], cleanup['id']),
    )
