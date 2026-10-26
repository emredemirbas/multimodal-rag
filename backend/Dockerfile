FROM python:3.12.10-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY pyproject.toml setup.cfg ./
COPY app ./app
RUN pip install --no-cache-dir .

USER app
EXPOSE 8000

FROM runtime AS ingestion-worker
CMD ["celery", "-A", "app.jobs.worker:celery_app", "worker", "--hostname=ingestion@%h", "--queues=ingestion", "--concurrency=2", "--loglevel=INFO"]

FROM runtime AS media-worker
CMD ["celery", "-A", "app.jobs.media_worker:celery_app", "worker", "--hostname=media@%h", "--queues=media", "--concurrency=1", "--loglevel=INFO"]

FROM runtime AS visual-worker
CMD ["celery", "-A", "app.jobs.visual_worker:celery_app", "worker", "--hostname=visual@%h", "--queues=visual", "--concurrency=1", "--loglevel=INFO"]

FROM runtime AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
