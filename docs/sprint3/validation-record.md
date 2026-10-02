# Sprint 3 local baseline validation

Date: 2026-10-02

Status: Local offline-baseline infrastructure validated. Provider-backed Alpha 1
approval remains open; no managed provider or paid request was enabled.

## Scope

- Separately bounded PostgreSQL full-text and exact pgvector retrieval, source
  filtering, deduplicated RRF fusion and deterministic identifier-aware reranking.
- Context diversity/size limits and conservative extractive abstention.
- Deep-snapshot citation validation and retained processing-generation metadata.
- Additive migration 0004 for scoped conversations, paired immutable turns,
  authoritative citations and atomic retrieval/usage attribution.
- Authenticated SSE answer delivery, saved history and same-key retry/replay.
- Scoped evidence inspection, precise timestamps and preservation of older
  evidence after reprocessing; no invented player for transcript-only uploads.
- Source deletion removes derived chat turns; project deletion cascades all chat.
- Accessible labelled chat controls, honest offline-model wording, loading,
  empty/error/success/abstention states and delivery-stop recovery.

## Completed checks

- Full backend suite with PostgreSQL, Redis, MinIO and `TEST_REAL_WORKER=1`:
  **77 passed, zero skipped** on the final application version (16.97 seconds).
- Final focused concurrency/metric tests: **6 passed**. Concurrent same-key writes
  produce one turn, one retrieval run and one local logical-turn metric increment.
- Frontend: **12 files, 32 tests passed**; lint and typecheck passed.
- Production Docker application builds and Compose startup passed. Seven
  long-running services healthy; migration/volume initialization exited 0.
- Backend dependency compatibility: 52 packages, no conflicts.
- `git diff --check` and Compose configuration validation passed.
- Previous Sprint 1/2 live smoke checks passed against the Sprint 3 stack.
- Sprint 3 live smoke passed: actual queued upload, server-only credential proxy,
  SSE through Next.js, disconnection followed by persisted replay, idempotency
  conflict, CSRF rejection, source inspection, old-version stability after
  reprocessing, unsupported-question abstention and complete owned-test cleanup.

Backend tests also reject cross-tenant and same-tenant cross-project chat/evidence
access, mismatched/fabricated/provider-mutated evidence and oversized JSON bodies.
Delivery rechecks authorization/existence and stops when the cited source/turn is
deleted. Scope/foreign-key failure rolls back turn, citations and retrieval writes.

Frontend tests cover fragmented UTF-8/SSE frames, incomplete/malformed/oversized
streams, runtime contract validation, safe text rendering, keyboard focus,
unchanged-key retry, stop-delivery messaging, archived/read-only state and
same-origin body limits. The test-only `server-only` alias does not alter Next's
production server/client boundary.

## Live browser and defects found

A test-owned `Chat UI verification` project with a synthetic VTT was used to
send a source-filtered question and verify saved history after a page reload.
The UI showed the extractive quote, model attribution and millisecond timestamps.
No browser-console warnings/errors were observed in these flows.

The actual standalone deployment revealed that Next uses a container hostname in
`request.url`; an origin comparison to that internal URL rejected legitimate
browser writes. The proxy now checks the browser-facing Host/Origin instead,
with missing/foreign-origin rejection and a regression test. It does not use
arbitrary forwarded-host headers to bypass the check.

Narrow-window browser inspection found that the bounding rectangle of a wrapped
inline citation contains a gap between its text lines. Citation links now use
an inline-block touch target, and response completion restores question-input
focus after re-enabling it. Internal navigation uses the existing Next.js Link
component with citation prefetch disabled. The final narrow-window check followed
the citation to its evidence page and back, verified the original text,
00:01.250–00:05.500 timestamps and generation/parser metadata, and confirmed that
history survived a reload. An unsupported Kubernetes/TLS question abstained with
no citations, and keyboard focus returned to the question field after completion.
No browser-console warnings/errors were observed in the final flows.

The verified test-owned project, its synthetic VTT and saved turns were then
permanently deleted. Artifact cleanup completed, project reads returned 404, and
the existing browser tab was restored to the project list. No existing user
project or shared volume was deleted.

## Initial synthetic measurements

`synthetic-python-api-v1` contains 13 supported and 6 unsupported questions over
implementation-authored FastAPI, PostgreSQL and Pydantic/test transcripts. On
2026-10-02, both the in-memory and actual PostgreSQL path reported:

| Measurement | Result |
|---|---:|
| Recall@4 of labelled evidence | 1.0 |
| Supported questions citing expected evidence | 1.0 |
| Citation ownership precision | 1.0 |
| Unsupported-question abstention | 1.0 |
| PostgreSQL p95 combined retrieval/answer probe | 97.97 ms |

The timing includes the evaluation's explicit retrieval probe plus its answer
request, not an external-model/network production latency test. Citation ownership
precision is not an independent faithfulness judgement. These synthetic labels
are not independently reviewed and the fixtures are much simpler than real
tutorials. Results must not be presented as general semantic-model quality.

## Hosted CI

The owner's prior Sprint 2 commit `d0ba720` passed
[hosted CI](https://github.com/emredemirbas/multimodal-rag/actions/runs/36996316293),
including all four jobs, image startup, smoke checks and real worker recovery.
The workflow now also includes Sprint 3 smoke and synthetic measurements, but
these current workspace changes were not committed/pushed or run in hosted CI.

## Reproduce

```bash
docker compose up --build -d --wait --wait-timeout 120
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
backend/.venv/bin/python scripts/smoke_sprint1.py
backend/.venv/bin/python scripts/smoke_sprint2.py
backend/.venv/bin/python scripts/smoke_sprint3.py
PYTHONPATH=backend backend/.venv/bin/python scripts/evaluate_rag.py --postgres
cd frontend
npm run lint
npm run typecheck
npm test
```

Smoke/evaluation tests create and remove only owned temporary projects. The
process-death probe remains isolated to its own schema/Redis namespace/process;
shared services, volumes and existing user data are preserved.

## Remaining release gates

The owner must select/approve a managed provider, models, region/retention/spend
policy and independently reviewed evaluation material/threshold. Before enabling
paid generation, add provider-specific deadlines/retry classification, reserved
generation idempotency and real token/cost attribution; concurrent offline
computation is not a guarantee against duplicate remote charges.

Current streaming delivers validated persisted excerpts, not remote token-by-token
generation. Questions are self-contained; history is not implicit model context.
No true learned semantic reranker, hosted login, external documentation retrieval,
video player, ASR/media, assignment or grading feature is implied. See ADR 0013.
