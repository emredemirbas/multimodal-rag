import json
import logging
from uuid import UUID

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from ..vision.policy import HARD_SECONDS, SOFT_SECONDS, VISIBILITY_SECONDS
from .queue import worker_app
from .visual_processing import process_video
from .visual_publication import publish_visual

settings = Settings.from_env()
celery_app = worker_app('tutorial_visual', settings.broker_url, 'visual')
celery_app.conf.update(task_soft_time_limit=SOFT_SECONDS, task_time_limit=HARD_SECONDS,
    visibility_timeout=VISIBILITY_SECONDS, result_backend_transport_options={'visibility_timeout': VISIBILITY_SECONDS},
    broker_transport_options={**celery_app.conf.broker_transport_options, 'visibility_timeout': VISIBILITY_SECONDS})


@celery_app.task(name='tutorial.process_video', shared=False)
def process(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        process_video(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'visual_worker_unavailable', 'code': 'processing_unavailable'}))


@celery_app.task(name='tutorial.publish_visual', shared=False)
def publish(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        publish_visual(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'visual_worker_unavailable', 'code': 'processing_unavailable'}))
