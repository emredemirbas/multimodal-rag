import json
import logging
from uuid import UUID
from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from ..vision.policy import SOFT_SECONDS,HARD_SECONDS,VISIBILITY_SECONDS
from .queue import worker_app
from .descriptions import describe_frames

settings = Settings.from_env()
celery_app = worker_app('tutorial_descriptions',settings.broker_url,'descriptions')
celery_app.conf.update(task_soft_time_limit=SOFT_SECONDS,task_time_limit=HARD_SECONDS,
    visibility_timeout=VISIBILITY_SECONDS,result_backend_transport_options={'visibility_timeout':VISIBILITY_SECONDS},
    broker_transport_options={**celery_app.conf.broker_transport_options,'visibility_timeout':VISIBILITY_SECONDS})

@celery_app.task(name='tutorial.describe_frames',shared=False)
def describe(tenant_id,project_id,source_id,job_id,generation):
    try:
        repository = SourceRepository(PostgresStore(settings.database_url),S3ArtifactStore(settings),settings)
        describe_frames(repository,tenant_id,UUID(project_id),UUID(source_id),UUID(job_id),generation)
    except Exception:
        logging.getLogger('tutorial_workspace.jobs').error(json.dumps({'event':'description_worker_unavailable','code':'processing_unavailable'}))
