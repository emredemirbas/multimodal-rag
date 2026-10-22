# Multimodal Tutorial Learning Workspace

A local, zero-service-spend GitHub portfolio project: authorized programming
tutorials become searchable, citation-backed learning material. Assignments and
feedback remain on the roadmap; this is not a production/SaaS deployment.

Sprint 0 validated the transcript-to-cited-answer path. Sprint 1 adds the product
foundation around it:

- an accessible Next.js project workspace;
- authenticated, tenant-scoped project management;
- create, list, view, rename, archive, restore, and delete flows;
- additive PostgreSQL migrations and base processing-job tables;
- separate migration, API, frontend, PostgreSQL/pgvector, Redis, and MinIO
  Compose services;
- backend, PostgreSQL integration, frontend, and image-build CI jobs.

Sprint 2 adds bounded SRT/VTT uploads, retained artifacts, Celery ingestion,
transactional outbox delivery, timestamped/versioned chunks, processing progress,
retry/cancel/reprocess controls and tracked source/project file cleanup. Optional
official YouTube video/playlist metadata never downloads audiovisual content.
Sprint 3 adds a labelled offline extractive chat baseline with persisted SSE
delivery, source filters, hybrid rank fusion/reranking and inspectable stable
timestamp citations. Optional Ollama/Qwen3 4B now provides real local answers;
the default remains a keyless extractive demo. Optional Qwen3 Embedding 0.6B adds
real local multilingual semantic retrieval; default retrieval stays 64-D hash/
lexical. Old indexes are never mixed with the 1024-D model space. Binary media/ASR
stays disabled.
The initial Sprint 4 slice adds ordered playlist metadata snapshots, explicit
video-to-subtitle associations and bounded independent transcript processing.
Frame extraction, OCR/vision and full multimodal Alpha 2 remain unimplemented.

An optional isolated Whisper-base foundation now validates restricted WAV inputs
and transcribes short PCM windows locally. **Audio upload in the application is
still disabled** until its dedicated queue and original-audio cleanup workflow are
implemented. This is not full ASR ingestion or multimodal completion (ADR 0018).

Published transcripts can also be browsed directly in chronological, version-
pinned pages, without asking a question or invoking a model. Private unfinished
indexing batches are never exposed as evidence.

## Read first

1. [`docs/01-product-brief.md`](docs/01-product-brief.md)
2. [`docs/02-requirements.md`](docs/02-requirements.md)
3. [`docs/03-system-design.md`](docs/03-system-design.md)
4. [`docs/04-sprint-plan.md`](docs/04-sprint-plan.md)
5. [`docs/05-data-model-and-api.md`](docs/05-data-model-and-api.md)
6. [`docs/06-security-and-content-policy.md`](docs/06-security-and-content-policy.md)
7. [`docs/07-open-decisions.md`](docs/07-open-decisions.md)
8. [`docs/08-testing-and-evaluation.md`](docs/08-testing-and-evaluation.md)

Codex should also read [`AGENTS.md`](AGENTS.md) before making changes. Sprint
validation evidence is recorded in [`docs/sprint4/validation-record.md`](docs/sprint4/validation-record.md).
The free local model follow-up is in
[`docs/sprint3/local-model-validation.md`](docs/sprint3/local-model-validation.md).
Sprint 2 hosted CI passed for `d0ba720` after replacing the removed MinIO image.
The owner committed playlists/local answers as `feb762e`. Semantic commit `d979a08`
passed [hosted CI](https://github.com/emredemirbas/multimodal-rag/actions/runs/38263085923).
This does not cover the resumable-indexing follow-up; its hosted result has not
yet been verified. Evidence is recorded in
[`docs/sprint3/semantic-search-validation.md`](docs/sprint3/semantic-search-validation.md).

## Run locally

Create the ignored local configuration once:

```bash
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Replace the placeholder `DEVELOPMENT_AUTH_TOKEN` value in `.env` with the
generated value. Also replace the example PostgreSQL and MinIO passwords.
The API intentionally refuses to start when the development token is missing
or shorter than 16 characters.

Build and start the stack:

```bash
docker compose up --build -d
docker compose ps
```

Local services:

- project workspace: <http://localhost:3000/projects>
- API documentation: <http://localhost:8000/docs>
- API readiness: <http://localhost:8000/health/ready>
- MinIO console: <http://localhost:9001>
- PostgreSQL: `localhost:5433`

The `migrate` service runs pending SQL migrations before the API starts. Service
ports bind to `127.0.0.1` by default.

`ingestion-worker` processes uploads; `scheduler` dispatches the transactional
outbox, recovers abandoned jobs and cleans artifacts. Existing passwords and
volumes are reused. MinIO is built from pinned official source because its old
registry image is unavailable; the first build can take a few minutes. A one-shot
initializer assigns only its data volume to the non-root MinIO user. This archived
CE build is for local tests, not a production storage recommendation (ADR 0012).

In a project, choose an SRT/VTT file (UTF-8, at most 2 MB), select your rights
statement and click **Process transcript**. Work continues if you leave the page.
Retry uses the retained input; correcting malformed content requires a new upload.
Reprocessing preserves the last usable generation until replacement succeeds.
Semantic processing saves each completed batch privately, continuing in bounded
deliveries until the whole generation is ready. Worker loss or explicit retry
resumes from committed progress; an in-flight, uncommitted batch may be recomputed.
Cancel keeps saved batches for retry. Reprocess starts a new generation and removes
only its superseded unfinished staging, not published evidence or old citations.
Deletion immediately removes records, then displays tracked file cleanup status.
`YOUTUBE_API_KEY` is optional, server-side, and needed only for metadata imports;
leave it empty to use uploads without external credentials or provider calls.

After a playlist metadata import, its ordered video list shows missing transcripts
and per-video progress. In **Transcript belongs to**, select the video described
by your authorized subtitle; this records your assertion rather than verifying
alignment against a video. At most two linked transcript jobs run per playlist
by default (`PLAYLIST_CONCURRENCY=1..4`). Waiting for capacity does not consume a
processing attempt. A failed video does not discard the other indexed videos.
Retry it separately or upload corrected subtitles after its job becomes terminal.
Older metadata imports need **Reprocess source** to populate ordered entries.
Truncated snapshots are explicitly labelled. Deleting playlist metadata keeps
separately uploaded transcripts; deleting the project removes both.

Use **Chat with tutorial evidence** to ask a self-contained question, optionally
filter to one indexed source, and inspect each citation. History survives reloads.
Stopping delivery may leave a saved answer: reload history or resend the unchanged
question to replay it without another logical turn. Default answers are quoted
transcript excerpts; the optional local model explains conservatively matched
evidence. Neither mode is a general-purpose conversational tutor.
Deleting a source also removes saved turns quoting that source.

In **Source management**, choose **Read transcript** on an indexed subtitle.
Browse 50 timestamped segments per page and use **Inspect evidence** for the
stable citation record. Paging retains the same generation after reprocessing;
an older-generation notice offers **Open latest published transcript** explicitly.
Reading still works when a source uses a different search index or the project is
archived. Subtitle uploads have no playable video; no playback URL is invented.

## Optional local ASR foundation (operator verification only)

This is a private model boundary, not a product upload feature. It supports WAV
signed 16-bit PCM / 16 kHz / mono, at most 20 MB and 10 minutes in the validator;
each model request is at most 30 seconds. Future jobs must enforce rights, scope,
resumability and terminal original cleanup before accepting audio in the app.

Explicit setup downloads about 148 MB of public multilingual Whisper-base files
from a pinned revision, verifies every SHA-256 and retains only reusable weights:

```bash
docker compose build asr
docker compose --profile asr-setup run --rm --no-deps asr-model-install
docker compose --profile local-asr up -d --wait --wait-timeout 120 asr
```

Verify an **owned/authorized <=30-second** supported WAV, without printing recognized
text or storing it in application data:

```bash
docker compose --profile local-asr run --rm -T --no-deps --entrypoint python asr \
  -m app.asr.smoke --language en < /absolute/path/to/owned-probe.wav
```

Use `--language tr` or `auto` as appropriate. This only verifies the model boundary;
it does not create a project/source or replace the normal transcript upload path.
The service has no published port, app credentials or user-data mount. It denies
new sockets/outbound connections after binding its listener, uses fresh bounded
model children, and sends no audio to a cloud/paid provider. It requires Linux
seccomp support; missing isolation/weights fail closed. It is not a learner-code
sandbox. Ordinary startup and CI do not fetch Whisper weights. Existing `.env`
settings are unchanged. See [scope and follow-up](docs/sprint4/local-asr-plan.md).

The first private durable component adds migration 0010 for scoped, resumable ASR windows
and deterministic complete-run VTT assembly. It does not retain original audio,
call the model, publish partial evidence or enable a WAV API/form. The private
backend follow-up below supplies worker execution, original cleanup and adoption.
See [checkpoint scope](docs/sprint4/asr-checkpoints-plan.md).

The private backend follow-up adds a dedicated optional `media-worker`, one-window
queue continuations, temporary-original retirement/cleanup and atomic VTT handoff
to ordinary indexing (migrations 0011/0012). Original processing eligibility lasts
at most one hour; physical deletion is separately confirmed/retried by the scheduler.
Reindexing retains the VTT and ASR provenance, not the original audio. The existing
application still rejects WAV: bounded authenticated upload and machine-generated
inspection UI are the remaining step, not enabled by running the private worker.
See [media workflow](docs/sprint4/media-worker-plan.md).

## Optional real local AI (no API key or service bill)

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3:4b
ANSWER_PROVIDER=ollama docker compose --profile local-ai up -d api
```

Explicit setup downloads the official model (about 2.5 GB) and an Ollama image;
allow roughly 10 GB extra disk and a 16 GB-RAM machine for this CPU profile.
It uses local CPU/RAM/electricity, not a paid API. Cloud is disabled, the model port
is not published, and no credential is required. Questions never download weights.
The adapter has a one-call capacity gate and a 24-second deadline; retry if the
machine is busy. It unloads the model after each answer to limit idle RAM and
transient prompt retention. Weights remain in the `ollama_data` volume.

In the default retrieval mode, search is hash/lexical, not learned semantic. Questions need
matching identifiers/terms: weak matches abstain before invoking the model and
are labelled `local-evidence-policy`, not falsely attributed to Qwen. Generated
answers use only retrieved citation IDs, but reasoning can still be wrong;
inspect the evidence. Saved history is not implicit context. ASR/OCR is disabled.

Return to the lightweight demo without editing credentials:

```bash
ANSWER_PROVIDER=extractive EMBEDDING_PROVIDER=hash docker compose up -d api ingestion-worker scheduler
docker compose stop ollama
```

After setup, test the real model with an owned temporary project:

```bash
set -a
source .env
set +a
python3 scripts/smoke_local_model.py
```

### Optional local semantic search

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3-embedding:0.6b
EMBEDDING_PROVIDER=ollama ANSWER_PROVIDER=ollama docker compose --profile local-ai up --build -d api ingestion-worker scheduler frontend
```

This explicit download adds about 639 MB of public weights. Queries and uploads
never pull models. The approved manifest is pinned in the application; a different
manifest fails safely rather than corrupting an index. Keep API and worker on the
same `EMBEDDING_PROVIDER`. To persist the choice across normal Compose startup,
set `EMBEDDING_PROVIDER=ollama` and `ANSWER_PROVIDER=ollama` in your ignored `.env`;
do not copy the example over an existing configuration or change credentials.

For existing sources, use **Reprocess source**, wait for success and reload the
workspace. Validation-only sources without jobs need a fresh transcript upload.
The UI labels incompatible indexes and excludes them from search. Old saved
citations remain inspectable; failed reprocessing does not remove prior evidence.
Switching back to hash also requires explicit reprocessing for current search.

Search uses an English query instruction, exact project-filtered 1024-D vectors,
full-text candidates and a small identifier boost. The experimental raw-cosine
0.40 guard is not a confidence/faithfulness score: valid paraphrases may still be
rejected, and related-but-unsupported questions can still require model abstention.
This is not a broad model-quality certification. Source IDs/generations are always
validated. `ANSWER_PROVIDER=extractive` can use the same semantic index while
returning only literal evidence quotes without running the answer model.

CPU safety limits: eight chunks/batch, at most eight batches/64 segments per
delivery, no new inference after 48 seconds (existing 90/120-second task limits).
Unfinished work requeues after two seconds without consuming a failure retry;
the 2 MB / 20,000 cues / 10,000 chunks input bounds remain. A separate processing
delivery count and saved/total progress are shown in the UI. Target model space
and a chunk manifest are pinned: restore the original mode/parser to retry, or
Reprocess source after a configuration change. Queries retain six-second inference
and a shared 28-second retrieval/answer budget (answer inference at most 24 seconds).
The model receives the time remaining after query retrieval. Unknown usage stays null; local
token/model/space attribution is recorded and billed API cost is zero.

With semantic mode enabled, run the explicit owned-project probe:

```bash
set -a
source .env
set +a
python3 scripts/smoke_semantic_search.py
# Explicit 129-chunk, multi-delivery native worker/model probe:
python3 scripts/smoke_semantic_search.py --long
```

For default regression smoke scripts below, use hash/extractive mode. CI exercises
fake local embedding HTTP and real database/worker recovery, without model downloads.

Stop the stack without deleting data:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the
local data volumes. Optional model weights also live in a named volume;
`docker compose --profile local-ai down` stops the optional model container too.

## Authentication boundary

The local Compose stack uses a single development principal authenticated by the
server-side `DEVELOPMENT_AUTH_TOKEN`. The Next.js server forwards that token to
the API; it is never placed in a `NEXT_PUBLIC_*` variable or accepted from a
browser-controlled tenant selector.

`X-Tenant-ID` is no longer trusted. Direct local API requests require:

```bash
set -a
source .env
set +a
curl -H "Authorization: Bearer $DEVELOPMENT_AUTH_TOKEN" \
  http://localhost:8000/api/v1/projects
```

A trusted identity-gateway adapter is also available for later deployment
integration. Its trust and networking requirements are documented in
[`ADR 0011`](docs/adrs/0011-sprint1-identity-adapters.md).

## Test

Backend unit, API, authentication, lifecycle, and isolation tests:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=. pytest -m "not integration"
```

With the Compose PostgreSQL service running, exercise real migrations, pgvector,
project deletion cascades, audit events, and the base job schema:

```bash
cd backend
set -a
source ../.env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=. pytest -m integration --tb=short
```

Frontend checks:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Exercise the running Compose application with a disposable test project:

```bash
set -a
source .env
set +a
python3 scripts/smoke_sprint1.py
python3 scripts/smoke_sprint2.py
python3 scripts/smoke_sprint3.py
python3 scripts/smoke_transcript_viewer.py
```

Smoke checks verify project lifecycle plus actual queued upload/indexing,
reprocessing, safe failure/retry, citations and complete artifact cleanup of their
own temporary projects. The process-death integration test owns an isolated DB
schema, Redis key prefix and Celery process; it never kills the normal worker or
flushes shared Redis. CI runs these against its ephemeral Compose stack.

The transcript-viewer smoke also runs in optional semantic mode: it uses the
configured ingestion worker but makes no answer-generation calls. It verifies
53 segments across two pages, production SSR, escaped text, preserved generations,
archive reads and its own full cleanup. See
[`docs/sprint3/transcript-viewer-validation.md`](docs/sprint3/transcript-viewer-validation.md).

Record synthetic retrieval measurements from the repository root:

```bash
PYTHONPATH=backend python3 scripts/evaluate_rag.py
# With local PostgreSQL credentials exported:
PYTHONPATH=backend python3 scripts/evaluate_rag.py --postgres
```

The 19-question synthetic set is a regression check, not an independent,
provider-backed model-quality benchmark or Alpha 1 approval.

Resumable-indexing design and validation are in
[`docs/sprint3/resumable-indexing-plan.md`](docs/sprint3/resumable-indexing-plan.md)
and [`docs/sprint3/resumable-indexing-validation.md`](docs/sprint3/resumable-indexing-validation.md).
Its real-process probe kills only its own worker after a committed checkpoint,
then counts fixture embedding calls to prove no accepted batch was recomputed.
This tests recovery, not neural-model quality; native model smoke is separate.

The deterministic Sprint 0 proof remains available without Docker or model
credentials:

```bash
cd backend
PYTHONPATH=. python3 -m app.demo
```

## API

Project lifecycle:

- `POST /api/v1/projects`
- `GET /api/v1/projects?status=active|archived|all`
- `GET /api/v1/projects/{project_id}`
- `PATCH /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/archive`
- `POST /api/v1/projects/{project_id}/restore`
- `DELETE /api/v1/projects/{project_id}`

Source ingestion and recovery:

- `POST /api/v1/projects/{project_id}/sources/uploads` (multipart file, rights, idempotency key)
- `POST /api/v1/projects/{project_id}/sources` (allowlisted YouTube metadata only)
- `GET /api/v1/projects/{project_id}/sources`
- `GET /api/v1/projects/{project_id}/sources/{source_id}`
- `GET /api/v1/projects/{project_id}/jobs/{job_id}`
- `POST /api/v1/projects/{project_id}/sources/{source_id}/retry|cancel|reprocess`
- `DELETE /api/v1/projects/{project_id}/sources/{source_id}` (`202` cleanup ticket)
- `GET /api/v1/projects/{project_id}/cleanup/{cleanup_id}`
- `POST /api/v1/projects/{project_id}/cleanup/{cleanup_id}/retry`

Deprecated Sprint 0 validation compatibility endpoint (development/test hash mode only;
the product UI uses queued uploads):

- `POST /api/v1/projects/{project_id}/sources/transcripts`

Chat and evidence (PostgreSQL required):

- `POST /api/v1/projects/{project_id}/conversations` (title and idempotency key)
- `GET /api/v1/projects/{project_id}/conversations`
- `GET /api/v1/projects/{project_id}/conversations/{conversation_id}`
- `POST /api/v1/projects/{project_id}/conversations/{conversation_id}/messages` (question, source IDs, key; SSE)
- `GET /api/v1/projects/{project_id}/evidence/{segment_id}`
- `GET /api/v1/projects/{project_id}/sources/{source_id}/transcript` (published segments; optional `generation`, fixed 50/page; pages after 1 require a generation)
- `POST /api/v1/projects/{project_id}/questions` (stateless JSON answer, optional source IDs)

Operational endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health` (compatibility alias)
- `GET /metrics`
- `GET /api/v1/runtime` (authenticated mode/index configuration, no secrets)

Every project-owned repository operation is scoped by tenant and project. An
unknown, deleted, or differently scoped project returns the same safe `404`
shape.

## Confirmed first-release boundary

- Python backend programming tutorials
- Uploaded, user-owned, authorized, or appropriately licensed content
- Timestamped transcript plus selected meaningful frames
- Project-scoped hybrid retrieval with source and timestamp citations
- Generated backend coding case studies
- ZIP/file submission initially; Git integration later
- Deterministic tests plus rubric-grounded AI feedback
- Private single-user projects
- Docker Compose for local development
- Default keyless demo and optional free local models behind application-owned interfaces

## Core stack

- Frontend: Next.js / React / TypeScript
- API: FastAPI / Python / Pydantic
- Database: PostgreSQL, pgvector, and PostgreSQL full-text search
- Background work: Celery / Redis with PostgreSQL state, outbox and fenced leases
- Object storage: S3-compatible storage; MinIO locally
- Packaging: Docker and Docker Compose
- Untrusted code: a dedicated hardened runner in Sprint 6, not the API or normal
  worker containers

## Content constraint

Do not design the product around silently downloading arbitrary public YouTube
audiovisual content. Supported processing starts from uploaded, user-owned,
authorized, or appropriately licensed inputs. Public URLs may supply allowlisted
metadata but are not a license to download or retain media.
