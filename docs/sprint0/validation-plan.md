# Sprint 0 validation record

Date: 2026-09-21

## Goal

Validate the narrowest compliant product loop before broad feature work:

```text
private project
  → authorized SRT/VTT transcript bundle
  → timestamped transcript and selected frame evidence
  → project-filtered hybrid retrieval
  → cited answer or explicit abstention
```

## Implemented proof

- FastAPI/Pydantic API with project creation, transcript ingestion, source lookup,
  and questions.
- SRT/VTT timestamp parsing and sanitization.
- Optional pre-extracted frame candidates with novelty-based deduplication. The
  API never processes arbitrary binary media; that belongs in a later isolated
  media worker.
- Application-owned embedding and answer-provider protocols.
- Deterministic offline providers for repeatable tests and a no-credential demo.
- PostgreSQL persistence, full-text search, and exact pgvector search under
  tenant and project filters. No approximate vector index is created.
- Stable segment and frame identifiers, processing versions, timestamped
  citations, and citation ownership validation.
- Idempotent transcript ingestion and machine-readable errors.
- Structured request logs, request IDs, Prometheus-format counters, and stored
  retrieval-run attribution. Runs retain a query hash plus retrieved/cited segment
  IDs without putting prompt or transcript content in logs.
- Docker Compose services for the API, PostgreSQL/pgvector, Redis, and MinIO.

## Deliberately deferred

- Authentication provider integration; `X-Tenant-ID` is only a development
  adapter and must not be trusted in a deployed environment.
- Automated media download or extraction.
- Celery jobs, playlist orchestration, OCR, ASR, and provider-backed models.
- Next.js application shell, assignments, submissions, and sandbox execution.
- PostgreSQL RLS; repository-level scope enforcement is covered now and RLS is a
  planned defense-in-depth layer.

## Acceptance checks

Run the offline demonstration:

From the repository root:

```bash
PYTHONPATH=backend python3 -m app.demo
```

Reproduce the local retrieval latency baseline:

```bash
PYTHONPATH=backend python3 scripts/benchmark_sprint0.py
```

Repeated 2026-09-21 development-container runs completed 500 deterministic
queries with p95 below 0.1 ms and maximum latency below 1 ms. This measures only
in-process retrieval and answer construction over the sample bundle; it
intentionally does not claim PostgreSQL, HTTP, network, or managed-model latency.

Run tests:

```bash
PYTHONPATH=backend pytest backend
```

When PostgreSQL/pgvector is running, enable the opt-in integration test:

```bash
set -a
source .env
set +a
PYTHONPATH=backend pytest backend -m integration
```

Validate and start the container stack:

```bash
docker compose config --quiet
docker compose up --build
curl http://localhost:8000/health
```

OpenAPI is available at <http://localhost:8000/docs> in the local environment.

## Exit assessment

The code demonstrates the compliant central loop and supplies the decisions,
cost model, wireframes, migrations, tests, and observability required for the
Sprint 0 handoff. Real provider latency/cost and binary frame extraction remain
explicit inputs to the Sprint 1/2 implementation plan rather than hidden claims.

`docker compose config` was validated. The current Codex runtime could not open
`/var/run/docker.sock`, so container startup and the opt-in PostgreSQL integration
test must still be executed on a host account with Docker daemon access using the
commands above.
