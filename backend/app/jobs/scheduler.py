import json
import logging
from pathlib import Path
import signal
import time

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from ..sources.media import retire_unusable_audio
from ..sources.video import retire_unusable_video
from .dispatch import cleanup_once, dispatch_once, redeliver_unclaimed
from . import curriculum_dispatch
from .queue import delivery_route
from .worker import celery_app


def main():
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format='%(message)s')
    repository = SourceRepository(PostgresStore(settings.database_url), S3ArtifactStore(settings), settings)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def publish(row):
        task, queue = delivery_route(row['job_type'])
        celery_app.send_task(task, args=[row['tenant_id'], str(row['project_id']),
                              str(row['source_id']), str(row['job_id']), row['generation']], queue=queue, expires=600)

    def publish_curriculum(tenant_id, project_id, run_id):
        celery_app.send_task('curriculum.advance_run',
                             args=[tenant_id, str(project_id), str(run_id)], queue='curriculum', expires=600)

    while not stopping:
        try:
            retired = retire_unusable_audio(repository)
            retired_video = retire_unusable_video(repository)
            recovered = repository.recover_leases()
            redeliver_unclaimed(repository)
            sent = dispatch_once(repository, publish)
            cleaned = cleanup_once(repository)
            curriculum_recovered = curriculum_dispatch.recover_expired(repository.store)
            curriculum_redelivered = curriculum_dispatch.redeliver_unclaimed(repository.store)
            curriculum_sent = curriculum_dispatch.dispatch_once(repository.store, publish_curriculum)
            Path('/tmp/ingestion-scheduler-heartbeat').touch()
            if recovered or sent or cleaned or retired or retired_video or curriculum_recovered or curriculum_redelivered or curriculum_sent:
                logging.info(json.dumps({'event': 'scheduler_cycle', 'published': sent, 'recovered': recovered,
                                        'cleaned': cleaned, 'retired_audio': retired, 'retired_video': retired_video,
                                        'curriculum_published': curriculum_sent, 'curriculum_recovered': curriculum_recovered,
                                        'curriculum_redelivered': curriculum_redelivered}))
        except Exception:
            logging.error(json.dumps({'event': 'scheduler_unavailable', 'code': 'dependency_unavailable'}))
        for _ in range(30):
            if stopping:
                break
            time.sleep(0.1)


if __name__ == '__main__':
    main()
