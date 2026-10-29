"""Trusted curriculum delivery process; model workflows are registered separately."""

import json
import logging
from uuid import UUID

from ..config import Settings
from ..curriculum.delivery import RunDeliveryRepository
from ..curriculum.execution import StageExecutor, advance_run
from ..postgres import PostgresStore
from .queue import worker_app


settings = Settings.from_env()
celery_app = worker_app("curriculum", settings.broker_url, "curriculum")
# An unknown workflow fails explicitly. There is no synthetic/default generator
# and no environment-controlled module import. The next slice owns real adapters.
PROCESSORS: dict[str, StageExecutor] = {}


@celery_app.task(name="curriculum.advance_run", shared=False)
def advance(tenant_id: str, project_id: str, run_id: str):
    try:
        repository = RunDeliveryRepository(PostgresStore(settings.database_url))
        advance_run(repository, tenant_id, UUID(project_id), UUID(run_id), PROCESSORS)
    except Exception:
        # Leave a lost lease for scheduler recovery. Never leak processor input,
        # output, credentials or database errors through Celery exception logs.
        logging.getLogger("tutorial_workspace.jobs").error(json.dumps({
            "event": "curriculum_worker_unavailable", "code": "processing_unavailable",
        }))
