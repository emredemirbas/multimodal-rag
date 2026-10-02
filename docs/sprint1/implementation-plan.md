# Sprint 1 implementation plan

Date: 2026-09-21

Status: Implemented; local Docker/PostgreSQL validation passed on 2026-10-02.
The first hosted CI run remains pending until these changes are pushed.

## Outcome

Turn the Sprint 0 validation slice into a navigable, authenticated project
foundation without pulling transcript job orchestration or chat forward from
Sprints 2 and 3.

## Delivery slices

1. **Identity and project domain**
   - provider-neutral authentication boundary;
   - user, external identity, and tenant-membership records;
   - tenant-scoped create, list, view, rename, archive, restore, and delete;
   - audit records for project lifecycle changes.
2. **Persistence foundation**
   - additive PostgreSQL migration from the Sprint 0 schema;
   - source lifecycle metadata plus processing-job and attempt tables;
   - a serialized, separately runnable migration command.
3. **Web application**
   - Next.js project list and detail navigation;
   - accessible loading, empty, error, pending, and success states;
   - server-only API credentials and no browser-controlled tenant input.
4. **Local platform and CI**
   - frontend and one-shot migration services in Docker Compose;
   - liveness/readiness checks and localhost-only published ports;
   - backend, PostgreSQL integration, frontend, and image-build CI jobs.

## Explicitly deferred

- Celery ingestion jobs and upload progress belong to Sprint 2.
- Persisted streaming conversations and production RAG belong to Sprint 3.
- Vendor-specific hosted sign-in UX remains replaceable; Sprint 1 establishes
  and tests the trusted application boundary.

## Acceptance checks

- Every project lifecycle operation passes same-tenant positive and cross-tenant
  negative tests.
- Active and archived navigation behaves predictably, and restore is supported.
- Project deletion removes its current relational and derived records while
  retaining a non-sensitive audit event.
- Backend unit/API tests and real PostgreSQL integration tests pass.
- Frontend lint, typecheck, component tests, and production build pass.
- Docker Compose validates, services become healthy, and CI builds the API and
  frontend development images.
