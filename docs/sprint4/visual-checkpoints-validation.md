# Private visual checkpoint validation

Date: 2026-10-26
Scope: migration 0013 and private complete-result staging only, ADR 0021.

## Database and integrity evidence

New integration tests use real PostgreSQL/pgvector and isolated disposable schemas.
They seed explicitly synthetic private video/job fixtures; no public upload,
native request, original storage, object PUT or user-owned data is involved.

- Concurrent begin/save accepts exactly one complete snapshot. Duplicate delivery
  cannot overwrite OCR or count accepted frames/bytes/characters twice.
- Actual lease expiry/recovery produces a new token; the old claim cannot read or
  write. The replacement retrieves the same PNG/OCR/PTS/identity snapshot without
  that component calling a provider. This is **not a real video-worker SIGKILL**,
  exactly-once inference or per-frame native resume claim.
- Tenant/project/source/generation/token/initiating-actor mismatch, cancellation,
  revoked membership, deleted source/project and expired lease/eligibility are
  fenced. A concurrent membership deletion is actually blocked by the read
  transaction's key-share lock, then succeeds after it finishes.
- Input, language/engine profile, rights, job kind and stored identity/version/
  expiry/actor drift fail closed. A job already expired cannot initialize a run;
  real retry/recovery does not extend the original creation-bound deadline.
- Missing/changed PNG/OCR/hash/PTS/video/candidate/manifest/count/ordinal data is
  rejected on load. Mutable models are revalidated rather than trusted by type.
- Losing eligibility after writes rolls back the whole transaction. An actual
  database constraint rejecting the second frame leaves **zero** partial frames;
  the clean retry succeeds. Composite FKs reject a mismatched existing job/source.
- Source/project deletion cascades through run metadata and every staged PNG/OCR
  row. Existing generic object cleanup still completes without a new object here.
- Staging never reaches active_generation, source frame/segment counts, published
  processing_versions/content_segments, answers/citations or usage_events. Existing
  published evidence remains unchanged. Counts are private operational metrics,
  not model-time/billing/quality claims; logs exclude filenames/input fingerprints/
  images/OCR. Ordinary transcript/ASR claims do not consume pending visual jobs.
- Upgrade a real pre-0013 schema containing a published transcript. Apply 0013
  twice through the migration runner; all earlier checksums and stable citation
  IDs survive. No prior migration file is edited.

The complete local regression is run against **new** PostgreSQL/Redis/MinIO
containers with allowlisted test-only credentials, tmpfs data and
`TEST_REAL_WORKER=1`, without reading actual `.env` or touching application
DB/bucket/queues/volumes. Cleanup removes only exact newly returned container IDs.
Final full regression: **501 passed, no skips, 81.09 seconds**, including the
existing real worker/recovery/object-store regressions and 42 new visual DB cases.
The maximum accepted 20 frames/320,000 OCR code points roundtrip too, with 64,000
UTF-8 bytes per frame at the text limit; no normalization silently changes hashes.

## Native boundary regression

Rebuilt the native image with an explicit file list: checkpoint code and
psycopg/Boto3/Celery/FastAPI are absent. The actual private HTTP/native smoke checks
this absence before serving its authored card request. It passes in a new
network-none/read-only/resource-bounded container with no ports/mounts/credentials,
including actual kernel/child denial, PNG/Turkish OCR transport, PTS `[0, 10000]`
and profile-drift rejection. `quality_approval=not_established` remains; no broader
OCR or scene-quality approval is implied. Existing native CI checks remain active.

## Delivery boundary

No application migration or service restart was run locally; existing data and
private `.env` remain untouched. Migration 0013 will run through the normal
deployment migration step when the updated application is deliberately rebuilt.
Frontend files, dependencies and API/BFF capabilities are unchanged. Hosted CI
results must be reported for the actual pushed commit, separately from local tests.

Still required: video registration, durable raw reservation/expiry/confirmed
cleanup, dedicated executable queue/task budgets, atomic final object adoption,
published provenance/evidence/retrieval/citations and accessible UI. The current
WAV worker's 90/120-second limits were not broadened to fit a full visual call.
