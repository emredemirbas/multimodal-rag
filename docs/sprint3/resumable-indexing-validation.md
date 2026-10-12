# Resumable semantic indexing validation

Date: 2026-10-12
Status: Local reliability slice validated (ADR 0017), not general model quality,
production readiness or multimodal/assignment completion.

## Delivered

- Migration 0008: private scoped staging vectors, job target-space pinning,
  ordered chunk manifest, saved/total progress and independent delivery sequence.
- Eight-document batches and at most eight batches/64 new segments per delivery;
  unfinished work yields through the outbox with two-second delay, releasing its
  lease/playlist slot without consuming a failure retry. No-progress continuations
  fail within the existing retry budget. Original task/HTTP/lease limits remain.
- The initial 128-chunk semantic rejection is replaced with checkpointed work
  under existing 2 MB / 20,000 cues / 10,000 chunks limits. No new provider,
  model download, paid API, media input or original-media retention.
- Every save/promotion rechecks project, actor, source generation, lease token and
  target space; parser/model drift fails safely. Private staging never participates
  in search or evidence inspection. Promotion and activation are one transaction.
- Accepted batch tokens and cumulative execution durations are attributed once;
  unknown tokens remain null and billed API cost zero. In-flight calls without
  committed output may be recomputed; this does not promise exactly-once inference.
- Cancel retains progress for explicit retry. Reprocess removes only superseded
  unfinished staging; published evidence/citations remain stable. Source/project
  deletion cascades checkpoints and retains durable object cleanup behavior.
- Accessible progress counts, distinct automatic continuation/retry messaging,
  safe configuration-change recovery, structured count logs and aggregate gauges.

## Completed checks

- Full backend with PostgreSQL, Redis, MinIO and `TEST_REAL_WORKER=1`:
  **149 passed, no skips** (final application rerun: 54.00 seconds).
- Frontend **13 files, 47 tests passed**, lint/typecheck passed.
- **5 lint compatibility checks**, full npm audit **zero findings**.
- Production API/worker/scheduler/migration/frontend Docker builds passed;
  migration 0008 applies and repeats, diff/Compose checks pass, eight selected
  long-running services healthy. Existing user volumes/credentials were preserved.
- Default Sprint 1/2/3 live smoke regressions passed. The 19-question PostgreSQL
  hash regression retains 1.0 recall/expected-citation/ownership/abstention scores;
  combined p95 was 168.29 ms in this run. This is not a neural-quality or production
  latency benchmark. API/worker configuration was restored to local AI afterwards.
- Scoped tests cover 129 chunks across three deliveries with one failure attempt;
  no premature search publication; failed/duplicate/stale saves; cancel/retry;
  provider/parser drift; outbox publication-ack race; old citation stability;
  token/duration aggregation; source/project deletion and complete staging cleanup.
- Actual isolated Celery SIGKILL **after eight committed chunks**, followed by a
  replacement worker and continued deliveries: 129 chunks, two failure attempts,
  three deliveries and exactly one fixture embedding call per chunk. No accepted
  batch was recomputed. Duplicate completed delivery creates no new work. Only the
  test's own schema, S3 prefix, Redis namespace and processes were used/cleaned.
  This fixture verifies real queue/recovery semantics, not neural inference quality.

## Native model evidence and limits

`scripts/smoke_semantic_search.py --long` indexed a synthetic 129-chunk transcript
with actual retained S3 input, outbox/scheduler/worker and approved local Qwen3
embeddings: **three deliveries, one logical attempt**, with no model downloads.
On the final quote-only answer probe, native semantic search cited the expected
source in **1.04 seconds**, stable evidence inspection passed, and the production
SSR page displayed **129 of 129 segments saved**. Its temporary project/files were
deleted through the scoped API; cleanup completed and reads returned 404.

The first long probe indexed all 129 chunks successfully but Qwen3 4B answer
generation exceeded the existing 24-second inference deadline (safe HTTP 503,
26.394 seconds including retrieval). No unvalidated answer was published; its
test project/files were cleaned. The deadline was **not** relaxed and no provider
fallback added. Separate quote-only indexing/retrieval verification does not
establish generated-answer performance on large or repetitive corpora. CPU/model
load can still cause honest answer timeouts. A subsequent SSR assertion was
  corrected to ignore React's interpolation comment nodes; no UI code workaround
  or skipped assertion was introduced.

After restoring the configured semantic + Ollama answer mode, the independent
small native BFF/SSE/history/replay smoke passed: first validated answer **10.52 s**,
stable citation and policy abstention without answer inference. Its own project/
files were also cleaned. This small success does not negate the long-corpus timeout.

No existing user project was present at the initial read-only inventory. Smoke
checks still resolve/delete only their own exact IDs, never all projects or shared
queues/volumes. The ignored local model configuration/credentials are unchanged;
normal startup retains optional local AI. Commit/push is a separate owner-authorized
delivery step; the hosted result for this slice has not yet been verified.

Previous semantic commit `d979a08` passed
[hosted CI](https://github.com/emredemirbas/multimodal-rag/actions/runs/38263085923),
verified read-only during this turn. That hosted run does **not** cover these new
checkpoint changes. CI includes the new process-death probe without neural weights.

## Reproduce

```bash
docker compose up --build -d --wait --wait-timeout 120
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
# Isolate native indexing/retrieval from answer-model CPU variability:
ANSWER_PROVIDER=extractive EMBEDDING_PROVIDER=ollama docker compose up -d api ingestion-worker scheduler
python3 scripts/smoke_semantic_search.py --long
# Restore your configured local answer mode:
docker compose up -d api ingestion-worker scheduler
cd frontend
npm test
npm run lint
npm run typecheck
npm run test:lint-compat
npm audit --audit-level=high
```

Default smoke scripts require hash/extractive API+worker configuration first.
Do not run native probes concurrently on the single-model CPU service. Representative
quality evaluation, learned reranking, media/ASR/OCR and assignments/grading remain
separate roadmap work; no quality threshold or binary-retention decision is implied.
