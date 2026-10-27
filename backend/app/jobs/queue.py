from celery import Celery


def worker_app(name: str, broker: str, queue: str) -> Celery:
    app = Celery(name, broker=broker)
    app.conf.update(
        task_serializer='json', accept_content=['json'], task_ignore_result=True,
        task_acks_late=True, task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1, worker_cancel_long_running_tasks_on_connection_loss=True,
        task_soft_time_limit=90, task_time_limit=120,
        broker_transport_options={'visibility_timeout': 240, 'socket_connect_timeout': 3, 'socket_timeout': 5},
        broker_connection_retry_on_startup=True, broker_connection_max_retries=10,
        task_default_queue=queue, task_publish_retry=False,
    )
    return app


def delivery_route(job_type: str) -> tuple[str, str]:
    if job_type in {'transcript', 'metadata'}:
        return 'tutorial.process_transcript', 'ingestion'
    if job_type == 'visual_index':
        return 'tutorial.index_visual', 'ingestion'
    if job_type == 'asr':
        return 'tutorial.process_audio', 'media'
    if job_type == 'visual':
        return 'tutorial.process_video', 'visual'
    if job_type == 'visual_publish':
        return 'tutorial.publish_visual', 'visual'
    if job_type == 'visual_describe':
        return 'tutorial.describe_frames', 'descriptions'
    raise ValueError('Unsupported processing job type')
