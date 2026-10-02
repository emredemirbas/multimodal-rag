# Sprint 2 validation record

Date: 2026-10-02

Status: Transcript-first scope implemented and locally validated. No corrected
GitHub-hosted CI run or live YouTube provider request has been verified yet.

## Delivered scope

- Authorized, bounded UTF-8 SRT/VTT uploads with scoped idempotency and durable
  raw transcript retention in the local S3-compatible object store.
- Separate Celery ingestion workers and a scheduler/outbox dispatcher; PostgreSQL
  owns job state, attempts, leases, generation fences and processing versions.
- Timestamped chunks with stable cue provenance and versioned deterministic
  embeddings. Reprocessing activates new evidence only after successful indexing;
  unsuccessful replacement leaves the last successful generation searchable.
- Safe job progress, bounded recovery, retry, cancellation and reprocessing.
- Source/project deletion with immediate relational removal and durable,
  observable, retryable object cleanup.
- Accessible source-management UI with explicit rights selection, progress,
  actionable errors, named deletion confirmation and visibility-aware polling.
- Allowlisted official YouTube video/playlist metadata adapters. Metadata is
  separately labelled and does not become tutorial evidence without a transcript.
- Additive migration `0003_transcript_ingestion.sql`, scoped processing usage,
  safe stage logs and bounded-label operational metrics.

## Completed checks

### Backend and infrastructure

The final full backend suite, with `TEST_REAL_WORKER=1`, passed **65 tests with
no skips**. Coverage includes:

- authentication, tenant isolation and same-tenant cross-project isolation for
  sources, jobs, commands, worker claims and cleanup tickets;
- bounded multipart and streamed request bodies, required rights, encoding/type
  validation, parser identifier preservation and stable timestamped chunks;
- concurrent registration, idempotent replay/conflict, broker publication failure
  and database rollback after object upload with durable orphan cleanup;
- duplicate delivery, cancellation fences, expired leases, bounded retry
  exhaustion, reprocessing activation and preservation of prior evidence;
- deletion racing worker execution, storage deletion failure/retry and revocation;
- bounded metadata fixtures, URL allowlisting, missing-provider configuration and
  abstention for metadata-only sources;
- actual local MinIO upload/content integrity and complete test-owned prefix
  deletion;
- an actual test-owned Celery worker process killed during processing, followed by
  scheduler recovery, replacement worker execution and duplicate broker delivery.

The process-death test uses its own PostgreSQL schema, queue and Redis key prefix.
After killing only its own process, it advances only its own lease timestamps to
exercise recovery without waiting the full 180 seconds. It does not flush a shared
Redis database, stop the application worker or delete existing user objects.

Additional checks passed:

- dependency compatibility: 52 installed backend packages, no conflicts;
- Docker production builds for API, worker, scheduler, frontend and local MinIO;
- `docker compose config --quiet` and `git diff --check`;
- seven long-running Compose services healthy; migration and scoped MinIO volume
  permissions initialization exited with status 0;
- `scripts/smoke_sprint1.py`: real-stack authentication, project lifecycle,
  frontend rendering, cited answer and deletion;
- `scripts/smoke_sprint2.py`: actual outbox/worker/S3 upload, replay, indexing,
  cited answer, reprocessing, actionable malformed-input failure/retry, frontend
  rendering and source/project file cleanup.

Both smoke scripts create and remove only their own disposable projects. Existing
persistent volumes and user projects are preserved.

### Frontend and browser

- `npm run lint`: passed;
- `npm run typecheck`: passed;
- `npm test`: **9 files, 21 tests passed**;
- production Docker build: passed;
- `npm audit --audit-level=high`: zero reported vulnerabilities.

Component/server-action tests cover runtime contracts, file size and rights
controls, multipart idempotency, terminal/hidden-page polling, safe recovery
states, deletion confirmation and observable cleanup receipts. Credentials remain
at the server boundary rather than entering browser requests or bundles.

The production UI was exercised against the live Compose stack using an owned
temporary project:

1. Upload `examples/fastapi-intro.vtt` with an explicit rights assertion and
   observe ready/indexed state.
2. Reprocess it and observe generation 2 become active.
3. Upload the malformed fixture and observe the safe correction message; retry
   the unchanged invalid input and observe the same deterministic failure.
4. Reprocess the malformed source, cancel the queued generation and observe the
   terminal cancelled state.
5. Open the deletion dialog, verify the source name and cleanup wording, then
   select “Keep source”. Confirmed deletion and file cleanup are exercised through
   API/integration tests and the smoke script, not a browser confirmation click.

Normal flows had no observed browser-console errors. One retry overlapped a
frontend container rebuild and encountered a stale Server Action/page error. The
error boundary was corrected to avoid claiming that no change occurred and now
offers a full-page reload; subsequent checks used the fresh build successfully.
The temporary UI project and its retained files were removed through the scoped
API after verification.

### Observability

Job stages and cleanup are represented in PostgreSQL and safe structured logs.
The live metrics endpoint exposes bounded status labels and attempt durations;
HTTP routes are templates, and content/project IDs are not metric labels. Usage
records retain tenant/project/source/provider/model attribution. The local
deterministic embedding provider records zero billed cost.

## Reproduce

From the repository root, with configured ignored `.env` credentials:

```bash
docker compose up --build -d --wait --wait-timeout 120
docker compose ps --all
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
backend/.venv/bin/python scripts/smoke_sprint1.py
backend/.venv/bin/python scripts/smoke_sprint2.py
cd frontend
npm run lint
npm run typecheck
npm test
npm audit --audit-level=high
```

The backend test environment must have its development dependencies installed.
Integration tests use local PostgreSQL, Redis and MinIO ports from the environment.
The compatibility synchronous transcript endpoint remains restricted to
development/test; the new UI uses only asynchronous ingestion.

## Limits and outstanding verification

- Binary media, ASR/OCR, frame extraction, ordered playlist orchestration and
  later-sprint chat/assignment features are not implemented. They are not implied
  by metadata registration or permitted subtitle retention.
- Chunking uses deterministic sentence/timing/size heuristics. Deterministic
  embeddings verify infrastructure, not provider-backed semantic retrieval quality.
- Metadata adapter tests use synthetic official-response fixtures. No live
  YouTube key/API request or provider cost was exercised.
- Local object deletion was verified on the unversioned development bucket.
  Production storage, backup/version retention and a maintained storage service
  remain pre-beta decisions; this is not a production deployment certification.
- MinIO's old registry pull caused the
  [first hosted CI failure](https://github.com/emredemirbas/multimodal-rag/actions/runs/36986898019).
  The pinned official source build works locally and CI now includes the
  real-worker probe, but a corrected hosted run has not been triggered.
- No commit or push was performed as part of this implementation handoff.

See [ADR 0012](../adrs/0012-durable-transcript-ingestion.md) for the recovery,
retention, isolation and development-only storage decisions.
