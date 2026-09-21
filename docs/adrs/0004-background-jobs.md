# ADR 0004: Celery and Redis for background jobs

- Status: Accepted
- Date: 2026-09-21

## Context

ASR, OCR, frame processing, embeddings, and playlist processing are slow and
failure-prone. In-process FastAPI tasks do not provide durable retry semantics.

## Decision

Use Celery with Redis for heavy jobs, with database-backed job state,
idempotency keys, bounded retries, cancellation, and an outbox for important
transitions. Sprint 0 includes Redis in Compose but does not pretend synchronous
transcript parsing is the final job pipeline.

## Consequences

Workers can crash and retry without duplicating logical artifacts. Operations
must monitor queue depth, failures, and dead letters.
