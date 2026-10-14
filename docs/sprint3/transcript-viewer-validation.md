# Published transcript viewer validation

Date: 2026-10-14
Status: Earlier source/evidence UX slice implemented and locally validated.
Not multimodal completion, an independent quality benchmark or production approval.

## Delivered

- Direct **Read transcript** navigation from indexed source cards and retained
  evidence pages, including sources incompatible with the current search space.
- Authenticated tenant/project/source reads, fixed 50-segment chronological pages
  with stable ID tie-breaking, explicit generation on pages after the first.
- Successful old generations remain readable after reprocessing. Unpublished
  replacements/checkpoints, frames and metadata never become transcript text.
- One read-only repeatable-read snapshot for metadata/count/rows, no project write
  lock, and `Cache-Control: no-store` on successful private API reads.
- Index-only migration 0009; prior migrations and retained evidence unchanged.
  Durable processing caps remain unchanged. The browse ceiling also accommodates
  already-retained legacy one-segment/cue validation data.
- Server-only API credentials, strict runtime contracts, literal React text,
  accessible timeline/navigation/loading/empty/error states and a named older-
  generation recovery link. No invented subtitle video/player/download URL.
- No answer/model/artifact calls or fabricated usage from browsing. Existing safe
  route metrics/logs cover requests; no text or vectors are added to logs.

## Checks

- Full backend with PostgreSQL, Redis, MinIO and `TEST_REAL_WORKER=1`: **155 passed,
  no skips** (final run: 56.47 seconds). Initial full run found the old health-version assertion; it was
  updated for 0.9.0 and the complete suite passed again.
- PostgreSQL coverage: 103 legacy transcript segments with tied timestamps plus
  a frame, 50/50/3 pages, immutable evidence equality, explicit page/generation
  bounds, 10,001 legacy rows without silent truncation, partial index migration.
- Private semantic staging remains empty in browsing until full promotion;
  cancel/retry/reprocess across semantic/hash generations preserves old pages.
- Negative membership/tenant/project/source reads, archive inspection, source/
  project deletion, safe HTTP/auth/validation errors and no-store are covered.
- Actual source deletion interleaved between count and row reads: the in-flight
  request stays internally consistent, while its next request returns 404.
  This does not promise revocation of bytes already read/sent before deletion.
- Frontend **17 files / 60 tests**; lint, typecheck and real pinned lint adapter
  compatibility checks pass. Full npm audit reports **zero vulnerabilities**.
- Production API/worker/scheduler/migration/frontend Docker builds passed;
  migration applies and repeats. Compose configuration and diff checks pass.
- Previous default Sprint 1/2/3 real-stack smoke checks pass. The 19-question
  implementation-authored hash regression retains 1.0 recall/expected citation/
  ownership/unsupported abstention; combined p95 was **58.67 ms** in this run.
  This is not neural-model quality or production latency certification.
- `scripts/smoke_transcript_viewer.py` passed separately in both configured native
  semantic ingestion mode and the default hash mode, against production SSR:
  53 segments over two pages, correct links/timestamps, escaped hostile text,
  stable evidence, generation-2 reprocessing, old-generation notice, archive
  reads, source/project 404s and observable complete owned-artifact cleanup.
  No answer-generation call, model download or paid API was used.

Only smoke-owned projects/files and isolated test schemas/worker namespaces were
removed. Existing user data, public model weights, shared queues/volumes and ignored
`.env` credentials were preserved. Temporary default-mode regression settings were
restored to the machine's configured local AI afterwards.

The new smoke is included in CI without model weights. The hosted result for this
slice has not yet been verified; local success is not a hosted CI result. The earlier
checkpoint slice's hosted result is not inferred from local tests.

## Reproduce

```bash
docker compose build api frontend ingestion-worker scheduler migrate
docker compose up -d --wait --wait-timeout 120
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
python3 scripts/smoke_transcript_viewer.py
cd frontend
npm test
npm run lint
npm run typecheck
npm run test:lint-compat
npm audit --audit-level=high
```

This smoke follows the configured ingestion mode; semantic weights must already
be explicitly installed. Default CI remains keyless hash/extractive. Reading the
published transcript itself does not depend on model availability. Contextual chat,
representative quality review, binary media/ASR/OCR/vision and assignments/grading
remain separate roadmap work.
