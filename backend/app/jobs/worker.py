import json
import logging
from uuid import UUID

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from .processing import process_transcript
from .visual_indexing import index_visual
from .queue import worker_app

settings = Settings.from_env()
celery_app = worker_app('tutorial_ingestion', settings.broker_url, 'ingestion')


@celery_app.task(name='tutorial.process_transcript', shared=False)
def process(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        process_transcript(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        # A DB outage leaves a lease for scheduler recovery, rather than leaking a DSN to Celery logs.
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'worker_unavailable', 'code': 'processing_unavailable'}))


@celery_app.task(name='tutorial.index_visual', shared=False)
def process_visual_index(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        index_visual(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'worker_unavailable', 'code': 'processing_unavailable'}))
