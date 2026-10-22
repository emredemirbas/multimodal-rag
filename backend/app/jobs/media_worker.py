import json
import logging
from uuid import UUID

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from .media_processing import process_audio
from .queue import worker_app

settings = Settings.from_env()
celery_app = worker_app('tutorial_media', settings.broker_url, 'media')


@celery_app.task(name='tutorial.process_audio', shared=False)
def process(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        process_audio(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'media_worker_unavailable', 'code': 'processing_unavailable'}))
