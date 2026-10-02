import json
import logging
from uuid import UUID

from celery import Celery

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from .processing import process_transcript

settings = Settings.from_env()
celery_app = Celery('tutorial_ingestion', broker=settings.broker_url)
celery_app.conf.update(
    task_serializer='json', accept_content=['json'], task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, worker_cancel_long_running_tasks_on_connection_loss=True,
    task_soft_time_limit=90, task_time_limit=120,
    broker_transport_options={'visibility_timeout': 240, 'socket_connect_timeout': 3, 'socket_timeout': 5},
    broker_connection_retry_on_startup=True, broker_connection_max_retries=10,
    task_default_queue='ingestion', task_publish_retry=False,
)


@celery_app.task(name='tutorial.process_transcript')
def process(tenant_id: str, project_id: str, source_id: str, job_id: str, generation: int):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
        process_transcript(repository, tenant_id, UUID(project_id), UUID(source_id), UUID(job_id), generation)
    except Exception:
        # A DB outage leaves a lease for scheduler recovery, rather than leaking a DSN to Celery logs.
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event': 'worker_unavailable', 'code': 'processing_unavailable'}))
