# Free local answer mode validation

Date: 2026-10-11
Status: Implemented and locally validated for the owner's portfolio target;
not production or general model-quality certification.

## Delivered

- Default keyless extractive mode plus explicit optional Ollama/Qwen3 4B answers.
- Official Ollama 0.40.3 image, non-root UID, read-only root, private model port,
  six-GiB/eight-CPU limits, one loaded model/request slot and disabled cloud features.
- Explicit 2.5-GB model download to an optional Docker volume; no API key, paid
  service, automatic weight pull, proxy, redirect, tool or implicit chat history.
- Local-only endpoint/model allowlists, bounded response bodies and deadlines,
  strict structured answers with retrieved-ID enums and server citation validation.
- One-call application capacity gate, honest model missing/busy/failure recovery.
- Migration 0006 for model manifest lookup and actual returned token attribution,
  atomic with turns/retrieval, zero billed API cost and null unknown usage.
- New-generation archive/history-limit preflight without blocking saved replay.
- Honest runtime-mode UI and application-side lexical abstention attribution.

## Checks

- Full backend with PostgreSQL, Redis, MinIO and real isolated worker probes:
  **115 passed, no skips** (42.06 seconds).
- Frontend **13 files, 40 tests passed**, lint and typecheck passed.
- Previous Sprint 1/2/3 live smoke checks also passed in default extractive mode.
  The 19-question PostgreSQL synthetic regression retained 1.0 recall/ownership/
  expected-citation/abstention scores (137.6-ms combined p95); this is not a local
  neural-model benchmark or general semantic quality claim.
- Clean `npm ci`, **5 real lint compatibility checks**, full audit **zero findings**.
  The framework/accessibility rules and full CI audit gate remain enabled. The
  tested private root-glob adapter removes braces/micromatch code, not its label.
- Backend/frontend/optional model production Docker builds passed. Migration 0006
  was applied from an explicitly rebuilt migration image and repeats safely.
- All eight selected runtime services are healthy. The model port is unpublished;
  a previously existing host service on port 11434 was left untouched.
- After regression checks the API was returned to local Ollama mode. The ignored
  `.env` credentials were not edited; ordinary default startup remains extractive.
- Real native model answer passed through FastAPI, Next's authenticated BFF and
  persisted SSE. It cited the owned VTT segment, contained GET /health and replayed
  the same key/turn. First validated delivery in the final probe took **11.15 s**.
- Unsupported Kubernetes/TLS input was rejected by the application's conservative
  evidence policy **without a model call**, with its own provider/model/prompt
  labels and zero tokens. Do not report that as independent model abstention quality.
- History and SSR local-mode wording passed. The owned test project and uploaded
  transcript were permanently deleted; artifact cleanup completed and reads returned
  404. No user project, shared queue, host model service or persistent user volume
  was deleted. Reusable public model weights remain available.

Native testing initially revealed an invalid delivery and inconsistent model-level
unsupported-question handling. Failures did not publish unvalidated answers, and
their test artifacts were cleaned. The final adapter constrains citation strings
to the retrieved ID enum and requires at least 50% meaningful term overlap before
inference. It still validates ownership, immutable generation and output shape.
This is deliberately conservative: legitimate paraphrases can be rejected.

Fake local HTTP tests cover unavailable/missing models, malformed/truncated/large
responses, foreign/duplicate citations, forbidden tool calls, invalid usage,
capacity, no-evidence requests and refusal of cloud/remote configuration. Integration
tests cover token/manifest persistence and archive rejection before model invocation
while preserving saved replay. The model unloads after generation (`keep_alive=0`)
to bound idle RAM/transient prompt retention; it does not train on uploads.

## Reproduce

```bash
docker compose up --build -d --wait --wait-timeout 120
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3:4b
ANSWER_PROVIDER=ollama docker compose --profile local-ai up -d api
set -a
source .env
set +a
python3 scripts/smoke_local_model.py
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
cd frontend
npm ci
npm run test:lint-compat
npm audit --audit-level=high
npm test
npm run lint
npm run typecheck
```

Default CI does not start/download the optional model; its HTTP/provider tests are
synthetic, plus actual ingestion/recovery tests. Real-model smoke is explicit.
These changes are uncommitted/unpushed; no hosted CI success is claimed.

## Remaining work and limits

Retrieval remains 64-D deterministic hash/full-text, not learned semantic search.
The tiny real-model fixture is not a representative faithfulness benchmark. Local
semantic embeddings require version filtering/reprocessing before replacing that
space. ASR/OCR/vision, binary media isolation/retention and assignments/grading are
not implemented here. CPU latency varies and the model can still reason incorrectly;
inspect source evidence. Local hardware/disk/electricity are required even though
no API/service fee is incurred. See ADR 0015 and README setup/resource notes.
