# Automatic private video workflow verification

Date: 2026-10-27. Scope: ADR 0025 and migration 0017, not public MP4 upload or
representative OCR quality approval. Hosted results are checked separately after
push; the results below describe the tested local tree.

## Software, migration and process-loss evidence

- Final full backend run: **645 passed, zero skipped, 170.04 seconds**, with
  `TEST_REAL_WORKER=1`. Fresh test-only PostgreSQL/pgvector, Redis and MinIO used
  random loopback ports and disposable memory-backed data, not application `.env`
  or user volumes. Teardown removed only recorded new container IDs. One existing
  upstream Starlette/httpx TestClient deprecation warning remains unsuppressed.
- New tests cover concurrent acceptance/delivery, automatic/manual idempotency,
  original receipt replay after completion/configuration change, once-only usage,
  scoped input/child FKs, blank OCR, no partial retrieval, cancellation and
  original-initiator retry, revocation, scope/token/generation fences, archived
  continuation, registration-pinned target vs visual-worker defaults, mismatch
  failure/retry and complete source/project deletion at multiple stages.
- Inject failure after child job/outbox creation at each handoff: parent status,
  usage, raw retirement, gallery marker/adopted row, child identity and outbox all
  roll back. Already committed extraction/first-frame work remains reusable.
  Unique failed S3 candidates are independently cleaned without deleting accepted
  PNGs. Also expire the actual parent wall-clock lease after child creation, then
  recover/redeliver and verify one accepted child.
- Actual owned Celery SIGKILL/saved-extraction recovery now runs in both manual
  and automatic modes. Replacement skips original GET and provider construction;
  automatic mode creates exactly one scoped gallery child while retiring raw.
  The pre-existing real frame post-PUT crash and saved-embedding SIGKILL probes
  still pass. In-flight inference remains at-least-once, not exactly-once.
- Additive migration/old published transcript ID/content/checksum preservation and
  repeat migration tests pass. Applied files 0001–0016 are untouched; old rows are
  not silently opted into the workflow. No new dependencies or public API fields.
- Unchanged frontend, checked in the existing production builder with Node
  24.21.0 and network disabled: **27 files / 143 tests**, five real lint-adapter
  compatibility tests, ESLint with zero warnings, and TypeScript checks pass.

## Actual native/application evidence

Rebuilt separately tagged API, ingestion and visual-worker images from the final
backend tree. Used the existing unchanged minimal native and production frontend
images. A fresh UUID-named Compose project, explicit test-only credentials, no
environment file, random ports and new validated non-external volumes ran actual
PostgreSQL/Redis/MinIO, scheduler, API, both trusted workers, isolated native visual
service and production frontend. Existing user services were not restarted.

The controlled authored English/Turkish-card MP4 produced actual local OCR and
two retained frames at decoded PTS 0 / 10,000 ms. Private automatic acceptance
alone reached generation 3; neither gallery nor initial index was manually queued.
Confirmed protected frame/API/production SSR and BFF/SSE/history citations,
original extraction identity, exact point timestamp and unreviewed-OCR labels.
No fake transcript or original-video player was introduced. A later explicit
internal reindex to generation 4 preserved old evidence, replay and chat history
with no additional native extraction for that workflow. Unauthenticated and
foreign-project reads were rejected. Raw deletion was independently confirmed;
only the two adopted PNGs remained. API project deletion then removed evidence,
workflow/derivative records and all scoped objects after verified cleanup.

Also executed the exact committed `scripts/smoke_video_workflow.py` against that
fresh production stack with a second authored fixture. It independently verifies
automatic generation-3 handoffs, all three original-actor jobs, two zero-billed
usage records, pinned target/receipt replay, Turkish OCR, actual frame citation,
protected API/SSR/PNG, independently confirmed raw deletion and its own complete
project/object cleanup. CI's image job now pipes the isolated native fixture
generator into this opt-in smoke after installing backend dependencies.

Both native probes passed again with final rebuilt images. Teardown removed only
the validated fresh Compose project's volumes/networks. Application `.env` remains
ignored/mode 0600; user data, running services and their migration state were not
changed. Local model weights were not downloaded and no paid/cloud call occurred.

## Remaining gates

Public MP4 capability, bounded multipart API/BFF, accessible consent/upload and
video raw-cleanup status UI remain the next slice. No public video reprocess,
playlist association, audio transcription, scene detection, vision description or
quality approval is enabled. Authored diagnostic cards do not establish technical
code-OCR accuracy, representative frame recall or real semantic retrieval quality.
