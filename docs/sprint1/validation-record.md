# Sprint 1 validation record

**Initial validation:** 2026-09-21

**Host validation completed:** 2026-10-02

## Implemented scope

- authenticated application shell with a provider-owned identity adapter;
- tenant- and project-scoped project create, list, read, rename, archive,
  restore, and delete operations;
- additive Sprint 1 database migration and a one-shot migration command;
- accessible Next.js project lifecycle UI;
- local Compose wiring for migration, API, frontend, PostgreSQL, Redis, and
  MinIO;
- CI jobs for backend tests, PostgreSQL integration, frontend checks, and image
  builds.

## Completed checks

### Backend

- `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -m "not integration"`:
  27 passed, 1 integration test deselected;
- Python bytecode compilation completed successfully;
- `pip check` completed without dependency conflicts;
- the Sprint 0 demo flow still passes.

The backend suite covers authentication failures, full project lifecycle,
cross-tenant isolation, same-tenant cross-project isolation, deletion cleanup,
health endpoints, and credential-safe database failure handling.

The final backend run also executed outside the restricted Codex sandbox. The
API deliberately sends synchronous PostgreSQL work through FastAPI's worker
thread pool, while the sandbox blocks even a minimal thread-pool wake-up. The
suite completes normally once that sandbox restriction is removed.

### Frontend

- `npm run lint`: passed;
- `npm run typecheck`: passed;
- `npm test`: 5 files and 11 tests passed;
- `npm run build`: production build passed.

The production build had to run outside the restricted Codex sandbox because
Next.js starts a TypeScript child process and the sandbox rejected that spawn
with `EPERM`. The same source then built successfully without the restriction.

### Browser lifecycle smoke test

The built frontend was exercised against the in-memory FastAPI application:

1. empty projects state;
2. create a project;
3. open project details;
4. rename;
5. archive and view the archived filter;
6. restore;
7. open and cancel the accessible delete confirmation dialog.

No browser-console errors were observed. Final deletion is covered by backend
tests; it was intentionally not confirmed during the browser smoke test.

### Platform configuration

- `docker compose config --quiet`: passed with validation environment values;
- Compose image resolution returned the expected frontend, API, PostgreSQL,
  Redis, and MinIO images.

## Host validation completed on 2026-10-02

Docker daemon access is now available outside the Codex sandbox. A random
development token was added to the ignored `.env` file, and its permissions were
set to `0600`. Existing passwords and persistent volumes were preserved.

The previous local virtual environment pointed at a different system Python
version. Its test dependencies were installed for the current Python 3.12
interpreter before running the complete backend suite.

Results:

- `docker compose up --build -d --wait --wait-timeout 120`: passed;
- `migrate`: exited with status 0;
- API, frontend, PostgreSQL, Redis, and MinIO: healthy;
- backend full suite with PostgreSQL: 31 passed, no skipped integration tests;
- fresh schema, preserved Sprint 0 project data on upgrade, repeatable migrations,
  and changed-checksum rejection: passed;
- real PostgreSQL API authentication and every cross-tenant project lifecycle
  rejection: passed;
- frontend lint, typecheck, and 11 tests: passed;
- frontend production build inside Docker without build-time secrets: passed;
- `scripts/smoke_sprint1.py`: passed against the updated live stack.

The smoke check creates its own disposable project, renders it through the
frontend, renames/archives/restores it, ingests a synthetic transcript, obtains
a cited answer, deletes its test project, and verifies project/source 404s.
It does not delete existing user projects.

The dependency scan found a newly published Next.js advisory. Next.js and
`eslint-config-next` were updated from 16.3.3 to 16.3.8, and the lockfile was
regenerated. The subsequent scan reported zero vulnerabilities. References:
[maintainer advisory](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j)
and [16.3.8 release](https://github.com/vercel/next.js/releases/tag/v16.3.8).

CI now builds the images, starts the complete stack, runs the same smoke check,
collects failure logs, and cleans up its own ephemeral volumes. The first
GitHub-hosted execution remains pending a push; local success is not presented
as evidence of a remote CI run.

Reproduce from the repository root:

```bash
docker compose up --build -d --wait --wait-timeout 120
docker compose ps
set -a
source .env
set +a
python3 scripts/smoke_sprint1.py

cd backend
PYTHONPATH=. .venv/bin/python -m pytest --tb=short
```

Local Sprint 1 validation is complete. Sprint 2 planning can proceed; the hosted
CI result must still be recorded after the first push.
