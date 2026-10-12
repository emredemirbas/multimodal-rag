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
the default remains a keyless extractive demo. Retrieval still uses the honest
64-D hash/lexical infrastructure baseline. Binary media/ASR stays disabled.
The initial Sprint 4 slice adds ordered playlist metadata snapshots, explicit
video-to-subtitle associations and bounded independent transcript processing.
Frame extraction, OCR/vision and full multimodal Alpha 2 remain unimplemented.

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
The owner committed Sprint 3 as `e31d186`. Current Sprint 4 changes have not been
committed/pushed; no hosted CI result for these new changes is claimed.

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

Retrieval is still hash/lexical, not learned semantic search. Questions need
matching identifiers/terms: weak matches abstain before invoking the model and
are labelled `local-evidence-policy`, not falsely attributed to Qwen. Generated
answers use only retrieved citation IDs, but reasoning can still be wrong;
inspect the evidence. Saved history is not implicit context. ASR/OCR is disabled.

Return to the lightweight demo without editing credentials:

```bash
ANSWER_PROVIDER=extractive docker compose up -d api
docker compose stop ollama
```

After setup, test the real model with an owned temporary project:

```bash
set -a
source .env
set +a
python3 scripts/smoke_local_model.py
```

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
```

Smoke checks verify project lifecycle plus actual queued upload/indexing,
reprocessing, safe failure/retry, citations and complete artifact cleanup of their
own temporary projects. The process-death integration test owns an isolated DB
schema, Redis key prefix and Celery process; it never kills the normal worker or
flushes shared Redis. CI runs these against its ephemeral Compose stack.

Record synthetic retrieval measurements from the repository root:

```bash
PYTHONPATH=backend python3 scripts/evaluate_rag.py
# With local PostgreSQL credentials exported:
PYTHONPATH=backend python3 scripts/evaluate_rag.py --postgres
```

The 19-question synthetic set is a regression check, not an independent,
provider-backed model-quality benchmark or Alpha 1 approval.

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

Deprecated Sprint 0 validation compatibility endpoint (development/test only;
the product UI uses queued uploads):

- `POST /api/v1/projects/{project_id}/sources/transcripts`

Chat and evidence (PostgreSQL required):

- `POST /api/v1/projects/{project_id}/conversations` (title and idempotency key)
- `GET /api/v1/projects/{project_id}/conversations`
- `GET /api/v1/projects/{project_id}/conversations/{conversation_id}`
- `POST /api/v1/projects/{project_id}/conversations/{conversation_id}/messages` (question, source IDs, key; SSE)
- `GET /api/v1/projects/{project_id}/evidence/{segment_id}`
- `POST /api/v1/projects/{project_id}/questions` (stateless JSON answer, optional source IDs)

Operational endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health` (compatibility alias)
- `GET /metrics`

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
- Managed model APIs behind application-owned provider interfaces

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
