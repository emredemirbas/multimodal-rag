# ADR 0002: Modular monolith with separate processes

- Status: Accepted
- Date: 2026-09-21

## Context

The product needs clear ownership boundaries but does not yet have scale or team
pressure that justifies independently deployed microservices.

## Decision

Use one Python application codebase with domain modules and separate API,
ingestion-worker, media-worker, and scheduler processes. Keep the Next.js web
application and hardened sandbox runner as separate deployment units.

## Consequences

Domain changes remain transactional and easy to refactor. Process boundaries can
scale independently. Modules must not bypass application-owned interfaces merely
because they share a repository.
