import json
import logging
from pathlib import Path
import signal
import time

from ..artifacts.storage import S3ArtifactStore
from ..config import Settings
from ..postgres import PostgresStore
from ..sources.repository import SourceRepository
from .dispatch import cleanup_once, dispatch_once, redeliver_unclaimed
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
        celery_app.send_task('tutorial.process_transcript', args=[row['tenant_id'], str(row['project_id']),
                              str(row['source_id']), str(row['job_id']), row['generation']], queue='ingestion', expires=600)

    while not stopping:
        try:
            recovered = repository.recover_leases()
            redeliver_unclaimed(repository)
            sent = dispatch_once(repository, publish)
            cleaned = cleanup_once(repository)
            Path('/tmp/ingestion-scheduler-heartbeat').touch()
            if recovered or sent or cleaned:
                logging.info(json.dumps({'event': 'scheduler_cycle', 'published': sent, 'recovered': recovered, 'cleaned': cleaned}))
        except Exception:
            logging.error(json.dumps({'event': 'scheduler_unavailable', 'code': 'dependency_unavailable'}))
        for _ in range(30):
            if stopping:
                break
            time.sleep(0.1)


if __name__ == '__main__':
    main()
