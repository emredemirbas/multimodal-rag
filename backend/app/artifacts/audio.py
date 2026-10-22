"""Terminal raw-audio retirement. Caller holds the scoped project lock."""
from uuid import UUID, uuid4

from .storage import object_prefix


def audio_prefix(tenant: str, project: UUID, source: UUID, generation: int) -> str:
    return f'{object_prefix(tenant, project, source)}audio/{generation}/'


def retire_audio(connection, tenant: str, project: UUID, source: UUID, job: UUID | None = None) -> int:
    rows = connection.execute(
        '''SELECT * FROM audio_inputs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
           AND (%s::uuid IS NULL OR job_id=%s::uuid) AND cleanup_id IS NULL FOR UPDATE''',
        (tenant, project, source, job, job),
    ).fetchall()
    for row in rows:
        cleanup = uuid4()
        # Derive the prefix from scoped identifiers, never a supplied object key.
        connection.execute(
            '''INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix)
               VALUES (%s,%s,%s,%s,%s)''',
            (cleanup, tenant, project, row['actor_user_id'], audio_prefix(tenant, project, source, row['generation'])),
        )
        connection.execute(
            'UPDATE audio_inputs SET cleanup_id=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s',
            (cleanup, tenant, project, source, row['job_id']),
        )
        connection.execute(
            '''UPDATE sources SET metadata=jsonb_set(metadata,'{audio_cleanup_id}',to_jsonb(%s::text)),updated_at=now()
               WHERE tenant_id=%s AND project_id=%s AND id=%s''',
            (str(cleanup), tenant, project, source),
        )
    return len(rows)


def record_audio_deleted(connection, cleanup: dict) -> None:
    connection.execute(
        '''UPDATE audio_inputs SET deleted_at=now() WHERE tenant_id=%s AND project_id=%s AND cleanup_id=%s
           AND deleted_at IS NULL''', (cleanup['tenant_id'], cleanup['project_id'], cleanup['id']),
    )
