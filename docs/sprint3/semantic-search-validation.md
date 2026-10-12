# Free local semantic retrieval validation

Date: 2026-10-12
Status: Implemented and locally validated for the GitHub portfolio target;
not a representative quality benchmark or production certification (ADR 0016).

## Delivered

- Optional private Ollama/Qwen3 Embedding 0.6B, approved manifest, 1024-D vectors,
  versioned query instruction and explicit 639-MB public weight download.
- Default repository startup remains hash/extractive and downloads no weights.
  No paid API, cloud fallback, redirects, proxy, tools or implicit chat history.
- Migration 0007 preserves immutable old evidence and separately filters vector
  spaces before distance calculation, in both lexical and semantic channels.
- Durable worker batching, input/CPU/request bounds, generation fences, preserved
  old index on failure, explicit reprocessing and unchanged complete deletion.
- Query/document token attribution, space/dimension/manifest metadata, unknown
  counts null and zero billed API cost; no content/vector/credential logging.
- Experimental raw-cosine relevance screen and cosine/identifier ranking;
  source-filtered exact search, authoritative timestamp/version citations.
- Honest mode, reindex and recovery UI. The chat BFF now preserves only allowlisted
  safe recovery codes instead of dropping all model errors into a generic message.
- Shared 28-second retrieval/answer budget under the 30-second web boundary,
  answer inference capped at 24 seconds; no fabricated fallback on timeouts.

## Checks

- Full backend with PostgreSQL, Redis, MinIO and isolated real-worker probes:
  **142 passed, no skips** (44.41 seconds); final repeat with the semantic local
  environment also passes. Test-owned worker environments explicitly select hash
  mode, so CI/regression tests never depend on installed neural weights.
- Frontend **13 files, 45 tests passed**, lint and typecheck passed.
- **5 lint compatibility checks**, full npm audit **zero findings**.
- Backend/frontend production Docker builds, Compose configuration and diff
  whitespace checks pass. Migration 0007 applies/repeats safely; eight runtime
  services are healthy, with no published model port or Docker socket exposure.
- Default Sprint 1/2/3 real-stack smoke checks pass. The 19-question PostgreSQL
  deterministic regression retains 1.0 recall/expected-citation/ownership/abstention
  scores and 91.78-ms combined p95. These are **not neural-model quality scores**.
- Fake embedding HTTP tests reject wrong dimensions/counts, zero/nonfinite/boolean/
  oversized vectors, invalid tokens, malformed/large responses, redirects, missing/
  changed manifests (including changes during a call), remote/paid configuration,
  capacity and timeouts. Invalid input is actionable; transient errors are bounded.
- Database tests cover mixed **active** 64/1024-D sources, source/tenant/project
  filtering, failed/successful replacement, duplicate delivery, usage metadata,
  old chat citations, cancellation/input caps, complete source cleanup and upgrade
  preservation. No ANN index is introduced.

## Real model evidence

An exploratory native batch returned 1024-D vectors in 3.32 seconds. The exact
query-instruction/weight manifest is recorded in ADR 0016. Small English/Turkish
health paraphrases scored above the experimental 0.40 floor, while unrelated
Kubernetes/TLS and geography questions scored below it. A Turkish validation
question scored about 0.389 for the intended Pydantic passage and 0.383 for a
transaction passage: this demonstrates ambiguity/possible valid-question
abstention, not universal multilingual quality or a calibrated threshold.

`scripts/smoke_semantic_search.py` passed with actual outbox/worker/S3 processing
and semantic retrieval in quote-only mode (supported calls 1.43/2.07 seconds).
It then passed on the final **semantic + Qwen3 4B answer** build:

- “Which route tells me the server is alive?”: cited the health passage, **9.81 s**.
- Turkish “Uygulamanın çalışıp çalışmadığını hangi adresten anlayabilirim?”:
  cited the same 00:01.250 evidence, **10.13 s**.
- Kubernetes/TLS and France-capital questions: policy abstention without citations
  or answer-model inference, **0.99/0.93 s** including query embeddings.
- Source reprocessing preserved generation-1 evidence and exact timestamps;
  SSR displayed the semantic model/index mode correctly.

`scripts/smoke_local_model.py` also passed native authenticated BFF/SSE delivery,
history, same-key replay and unsupported policy behavior on the combined index.
First validated delivery took **9.91 s**. A first attempt exposed a too-short
16-second cold CPU inference cap; it failed safely without publishing an answer.
The final shared budget resolves that observed case while retaining deadlines.
CPU load and larger evidence can still cause honest timeouts/abstention.

All smoke-owned projects/files, including the failed probe, were permanently
deleted through scoped API cleanup. The owner's exact empty **FastAPI Deneme**
test project was also deleted with their explicit permission; cleanup completed
and its reads returned 404. No other user project, shared queue, persistent data
volume or pre-existing host Ollama service was deleted. Public model weights remain.

The ignored local `.env` now selects `COMPOSE_PROFILES=local-ai`,
`EMBEDDING_PROVIDER=ollama`, `ANSWER_PROVIDER=ollama`, so normal startup retains
this machine's verified mode. Credentials were unchanged; permissions remain 0600.
The repository example remains keyless hash/extractive. Commit/push is a separate
owner-authorized delivery step; hosted CI for this slice has not yet been verified.

## Reproduce

See README for explicit model installation and switching/reindexing modes.

```bash
docker compose up -d --wait --wait-timeout 120
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
python3 scripts/smoke_semantic_search.py
python3 scripts/smoke_local_model.py
cd frontend
npm test
npm run lint
npm run typecheck
npm run test:lint-compat
npm audit --audit-level=high
```

For default regression smoke scripts, explicitly select hash/extractive for both
API and worker first. Never run model smoke probes concurrently against the
one-model CPU service. Tests create/delete only their own namespaces/projects.

## Remaining limits

The 0.40 guard is experimental and can accept related unsupported evidence or miss
valid paraphrases. Citation ownership is not faithfulness proof. Representative
owner-reviewed tutorial/question labels and threshold review remain necessary
before broad quality claims. Large transcript resumable semantic batching, learned
reranking, local ASR/OCR/vision, binary-media limits/retention/isolation, assignments
and grading are not implemented by this slice. Hardware/electricity/storage are
still required; “zero billed API cost” is not zero resource use.
