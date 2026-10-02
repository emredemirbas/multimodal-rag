# Sprint 2 implementation plan

Date: 2026-10-02

Status: Implemented and locally validated. See `validation-record.md` for
test evidence, current limits and deployment/provider limitations.

## Outcome

A user adds an authorized SRT/VTT transcript to a private project, leaves the
page while a separate worker processes it, and returns to timestamped indexed
segments or a safe, actionable failure. Retrying, cancelling, reprocessing,
worker crashes, and project deletion must not duplicate or resurrect artifacts.

Sprint 1 local validation passed, including real PostgreSQL, migration upgrades,
image builds, and the live application smoke check. Its first hosted CI run
failed at the old MinIO registry pull after the first push. The source-built
local/CI replacement is verified locally and hosted run 36996316293 passed after
the owner's push of `d0ba720` on 2026-10-02.

## Scope and assumptions

- SRT/VTT uploads are the first complete processing path, as accepted in ADR
  0001. Start with a configurable 2 MB byte limit and UTF-8/UTF-8-BOM input.
- Users explicitly select owner, authorized, or licensed input before upload.
  Rights assertions and retention class are persisted; no default implies rights.
- Reuse the deterministic embedding provider for reproducible infrastructure
  tests. Record its provider, model, dimensions, version, usage, and zero billed
  cost. Provider-backed retrieval quality remains an Alpha 1 evaluation task.
- YouTube video/playlist URLs supply allowlisted metadata. They never authorize
  audiovisual downloading or captions acquisition. Ordered playlist processing
  and frame extraction remain Sprint 4 work.
- Raw uploaded transcripts may be retained as permitted source artifacts for
  retry/reprocessing and deleted with the source/project. Original binary media
  retention must be explicitly selected rather than inherited from that policy.
- Managed ASR/provider and binary-media parsing requirements are not yet selected.
  They do not block subtitle uploads or metadata adapters. Before accepting binary
  media for processing, record that choice in the open decision log and an ADR.
  Until then, the API/UI must report the capability as unavailable, not queue a
  job that can never succeed.
- New product ingestion is asynchronous. Keep the synchronous Sprint 0 endpoint
  as a clearly documented validation compatibility path until its replacement is
  verified; do not wire the new UI to it.

## Ordered delivery slices

### 1. Source contracts and durable registration

Add application-owned normalized source, artifact, processing-version, job,
attempt, and failure contracts. Introduce an additive `0003` migration over the
existing source/job tables, plus source artifacts, processing-version metadata,
transactional outbox entries, and durable deletion work.

Every relationship and lookup carries tenant and project scope. Upload input
does not accept a tenant. Store an authenticated actor reference for worker-side
authorization, a content SHA-256, rights mode, and processing generation.

Implement registration and source/job reads:

- `POST /api/v1/projects/{project_id}/sources/uploads` -> `202` with source/job IDs;
- `GET /api/v1/projects/{project_id}/sources`;
- `GET /api/v1/projects/{project_id}/sources/{source_id}`;
- `GET /api/v1/projects/{project_id}/jobs/{job_id}`.

The upload limit applies to bytes before buffering and to the Next.js server
boundary as well as FastAPI. Validate supported filename, type, encoding, and
rights. Put the input under an application-generated
`tenant/project/source/generation` object key; never accept a caller's object key.

Use an application-owned S3 interface with MinIO locally. Source, job, and outbox
registration commit together. Handle the object-store/DB gap with a bounded,
observable orphan cleanup policy. A failed transaction must not leave a source
appearing queued without work to publish.

Idempotency is scoped by tenant/project/key. Replaying the same key and hash
returns the same source/job; reusing the key with different input returns `409`.
Concurrent requests must rely on transactional uniqueness, not only a preflight
lookup.

Acceptance: cross-tenant and same-tenant cross-project rejection, bounded upload,
rights/encoding errors, duplicate/conflicting/concurrent registration, broker-down
registration, and rollback cleanup pass against PostgreSQL and MinIO.

### 2. Real worker, outbox dispatcher, and processing

Add a dedicated ingestion-worker image and a separate scheduler/dispatcher
process in Compose. Pin Celery/Redis dependencies and the Python environment;
keep the domain code in the modular monolith.

Queue messages contain only tenant, project, source, job, and generation IDs.
Workers recheck live project/source state and authorization before reading the
artifact or committing output. Transcript text, signed URLs, credentials, and
raw exceptions do not travel in task arguments or task-result logs.

The dispatcher claims outbox rows with a bounded lease and publishes to Redis.
Publication and acknowledgement gaps may redeliver messages; DB claim/fencing
and artifact uniqueness make every task safe to run more than once. PostgreSQL
is the source of user-visible job state; Redis result storage is not an authority.

Worker stages:

1. validate the uploaded transcript and rights;
2. parse, sanitize, and normalize timestamps without losing code identifiers;
3. chunk at sentence/topic and timing boundaries while retaining original cue
   provenance, start/end timestamps, and configured size/duration limits;
4. compute versioned embeddings and atomically activate the indexed generation;
5. record attempt duration/usage and mark the source ready.

Stable segment IDs include source, generation/processing version, cue range, and
normalized content. Duplicate delivery of one generation must produce identical
IDs. Preserve older processing provenance when a new generation is activated;
future citations must not silently resolve to new text.

Use late acknowledgement and worker-loss recovery with bounded attempts. Set
explicit I/O timeouts, soft/hard limits, and Redis visibility timeout consistently.
Transient storage/provider failures use capped backoff with jitter; invalid
transcripts fail deterministically with a safe code and correction instructions.

Acceptance: an actual Celery worker produces indexed segments; duplicate
delivery does not duplicate artifacts; broker publication interruptions and
worker death recover under bounded attempts. Eager-mode tests supplement but do
not replace this real-process check.

### 3. Recovery, cancellation, reprocessing, and deletion

Add retry, cancel, reprocess, and source deletion commands under project scope.
Commands validate state transitions and use idempotency keys. Retry reuses the
logical generation; reprocessing creates a new version and atomically switches
the active generation only on success.

Cancellation is cooperative between stages and before every final write. A
stale worker must fail its generation/lease fence and cannot overwrite a newer
attempt. The scheduler recovers expired leases and marks exhausted jobs failed.

Before deleting source/project rows, persist minimal durable object cleanup work
that survives their cascades. Workers cannot resurrect deleted records. Relational
data becomes inaccessible immediately; object deletion is retryable and has an
observable completion state. Preserve the existing project delete contract unless
a documented API revision is necessary; do not describe scheduled cleanup as
already completed.

Acceptance: cancel-before-start and cancel-during-processing, repeat retry,
failed reprocessing with prior evidence preserved, deletion racing a worker,
storage deletion failure/retry, and full object/row cleanup all pass.

### 4. Accessible source management UI

Replace the project workspace placeholder with a source list, bounded SRT/VTT
upload form, rights controls, per-source processing stage/progress, and safe
failure/retry/cancel/reprocess/delete actions. Keep credentials in the Next.js
server API boundary.

Begin with an authenticated polling endpoint at a bounded interval and stop
polling terminal jobs or hidden pages. Add SSE only if the same scope/reconnection
contract is verified; streaming chat remains Sprint 3 work.

Provide labelled controls, keyboard focus, live status announcements, loading,
empty, success, partial-failure, and error/retry states. Delete confirms the named
source. UI text describes available behavior rather than internal sprint numbers.

Acceptance: upload -> processing -> ready, malformed input -> actionable failure,
retry/cancel/reprocess, and source/project deletion pass through the web UI;
component tests cover state and accessible controls.

### 5. Allowlisted metadata adapters and final sprint verification

Define `SourceAdapter` and `NormalizedSource` contracts shared by uploaded
transcripts and provider metadata. Parse supported HTTPS YouTube video/playlist
URLs into validated canonical IDs. Construct requests only to fixed official API
endpoints; reject arbitrary hosts, userinfo, custom ports, unsupported schemes,
and redirects. Apply bounded response size, timeout, pagination, and configured
playlist limits.

Implement video and playlist metadata adapters using the official Data API,
record retrieval time/provider/canonical ID and item order, and keep metadata-only
sources in a state that explicitly requests an authorized transcript. A missing
server-side API key returns `provider_not_configured`, not an unofficial fallback.
Use synthetic response fixtures for CI and isolate live provider tests.

Extend Compose/CI to test PostgreSQL, Redis, MinIO, dispatcher, and a real worker
together. Add safe structured stage logs and bounded-label job/attempt/duration
metrics. Persist tenant/project/source attribution for processing and model usage;
do not put identifiers or content into unbounded metric labels.

Final acceptance: all slices pass plus one end-to-end supported tutorial upload,
duplicate/retry recovery, actionable errors, and deletion of every derived
artifact. Record evidence in `docs/sprint2/validation-record.md` before marking
Sprint 2 complete.

## Suggested module boundaries

- `backend/app/sources/`: normalized adapters, contracts, commands, repositories;
- `backend/app/jobs/`: outbox, leases, attempts, worker task entry points;
- `backend/app/artifacts/`: scoped S3 access and durable cleanup;
- `backend/app/migrations/0003_*`: additive source/processing foundation;
- `frontend/src/components/sources/`: upload, source list, progress and actions;
- `scripts/smoke_sprint2.py`: real Compose upload/job/recovery/deletion proof.

These are implementation boundaries, not a requirement to split deployable
services or rewrite unrelated Sprint 1 code.

## References used for planning

- [Celery tasks: idempotency, acknowledgement and retries](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [Celery Redis transport and visibility timeout](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- [Official video metadata endpoint](https://developers.google.com/youtube/v3/docs/videos/list)
- [Official playlist-item metadata endpoint](https://developers.google.com/youtube/v3/docs/playlistItems/list)

The storage, lease/fencing, deletion and delivery-slice choices above are this
application's design proposals. They are not claims that Celery supplies these
domain guarantees automatically.
