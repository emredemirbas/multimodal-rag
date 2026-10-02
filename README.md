# Multimodal Tutorial Learning Workspace

A private learning workspace that turns authorized programming tutorials into
searchable evidence, practical assignments, and feedback.

Sprint 0 validated the transcript-to-cited-answer path. Sprint 1 adds the product
foundation around it:

- an accessible Next.js project workspace;
- authenticated, tenant-scoped project management;
- create, list, view, rename, archive, restore, and delete flows;
- additive PostgreSQL migrations and base processing-job tables;
- separate migration, API, frontend, PostgreSQL/pgvector, Redis, and MinIO
  Compose services;
- backend, PostgreSQL integration, frontend, and image-build CI jobs.

Transcript job orchestration remains Sprint 2 scope. Persisted streaming chat
remains Sprint 3 scope.

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
validation evidence is recorded under [`docs/sprint1/`](docs/sprint1/).
The 2026-10-02 host validation passed; the next implementation milestone is
described in [`docs/sprint2/implementation-plan.md`](docs/sprint2/implementation-plan.md).

## Run Sprint 1 locally

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

Stop the stack without deleting data:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete all
local PostgreSQL, Redis, and MinIO volumes.

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

## Test Sprint 1

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
PYTHONPATH=. pytest -m integration
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
```

The smoke check verifies health, authentication, frontend rendering, project
lifecycle, a cited answer, and deletion of its own test data. CI runs the same
check against its ephemeral Compose stack.

The deterministic Sprint 0 proof remains available without Docker or model
credentials:

```bash
cd backend
PYTHONPATH=. python3 -m app.demo
```

## Sprint 1 API

Project lifecycle:

- `POST /api/v1/projects`
- `GET /api/v1/projects?status=active|archived|all`
- `GET /api/v1/projects/{project_id}`
- `PATCH /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/archive`
- `POST /api/v1/projects/{project_id}/restore`
- `DELETE /api/v1/projects/{project_id}`

Retained Sprint 0 validation endpoints:

- `POST /api/v1/projects/{project_id}/sources/transcripts`
- `GET /api/v1/projects/{project_id}/sources/{source_id}`
- `POST /api/v1/projects/{project_id}/questions`

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
- Background work: Celery and Redis beginning in Sprint 2
- Object storage: S3-compatible storage; MinIO locally
- Packaging: Docker and Docker Compose
- Untrusted code: a dedicated hardened runner in Sprint 6, not the API or normal
  worker containers

## Content constraint

Do not design the product around silently downloading arbitrary public YouTube
audiovisual content. Supported processing starts from uploaded, user-owned,
authorized, or appropriately licensed inputs. Public URLs may supply allowlisted
metadata but are not a license to download or retain media.
