"""Atomic internal job handoffs. PostgreSQL/outbox, not a new workflow engine."""
from ..embedding_profiles import HASH_SPACE, QWEN_SPACE, configured_space
from ..sources.contracts import SourceError

VERSION = 'selected-ocr-v1'


def register(repository, connection, tenant, project, source, job, actor):
    connection.execute(
        '''INSERT INTO video_workflows (tenant_id,project_id,source_id,visual_job_id,
           visual_generation,actor_user_id,workflow_version,target_embedding_space)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
        (tenant, project, source, job.id, job.generation, actor, VERSION,
         configured_space(repository.settings.embedding_provider)),
    )


def _check(workflow, claim):
    if (workflow['workflow_version'] != VERSION or workflow['actor_user_id'] != claim['actor_user_id']
            or workflow['target_embedding_space'] not in {HASH_SPACE, QWEN_SPACE}):
        raise SourceError('processing_configuration_changed', 'The accepted video workflow identity changed.', 409)


def after_preparation(repository, connection, claim):
    """Called only inside successful fenced preparation, before its final clock check."""
    scope = tuple(claim[k] for k in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))
    workflow = connection.execute(
        '''SELECT * FROM video_workflows WHERE tenant_id=%s AND project_id=%s AND source_id=%s
           AND visual_job_id=%s AND visual_generation=%s FOR UPDATE''', scope,
    ).fetchone()
    if workflow is None: return None  # Legacy/manual video.
    _check(workflow, claim)
    if workflow['publication_job_id'] is not None:
        raise SourceError('invalid_video_state', 'The selected-frame handoff was already recorded.', 409)
    from .gallery import VisualGalleryRepository
    item = VisualGalleryRepository(repository).enqueue(*scope[:4], claim['actor_user_id'],
        f'workflow-{claim["id"]}-retain-v1', connection=connection, continuation=True)
    connection.execute(
        '''UPDATE video_workflows SET publication_job_id=%s,publication_generation=%s
           WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND visual_job_id=%s AND visual_generation=%s''',
        (item.job.id, item.job.generation, *scope),
    )
    return item.job


def after_publication(repository, connection, claim):
    """Called only inside complete fenced gallery adoption; no raw/native access."""
    scope = tuple(claim[k] for k in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))
    workflow = connection.execute(
        '''SELECT * FROM video_workflows WHERE tenant_id=%s AND project_id=%s AND source_id=%s
           AND publication_job_id=%s AND publication_generation=%s FOR UPDATE''', scope,
    ).fetchone()
    if workflow is None: return None
    _check(workflow, claim)
    if workflow['index_job_id'] is not None:
        raise SourceError('invalid_video_state', 'The OCR index handoff was already recorded.', 409)
    from .index import VisualIndexRepository
    item = VisualIndexRepository(repository).enqueue(*scope[:4], claim['actor_user_id'],
        f'workflow-{workflow["visual_job_id"]}-index-v1', connection=connection,
        target_embedding_space=workflow['target_embedding_space'], continuation=True)
    connection.execute(
        '''UPDATE video_workflows SET index_job_id=%s,index_generation=%s
           WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND publication_job_id=%s AND publication_generation=%s''',
        (item.job.id, item.job.generation, *scope),
    )
    return item.job
