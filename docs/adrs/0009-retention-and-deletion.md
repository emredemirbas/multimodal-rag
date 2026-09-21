# ADR 0009: Derived-first retention and complete deletion

- Status: Accepted
- Date: 2026-09-21

## Context

Original media increases privacy, rights, and storage risk. Deleting only
relational rows would leave vectors, objects, caches, or provider artifacts.

## Decision

Avoid original-media retention by default and store only permitted derived
artifacts. Give every artifact a retention class. Project deletion must cover
PostgreSQL rows, embeddings, object storage, cache entries, queued work, and
provider-held artifacts where deletion APIs exist.

## Consequences

Some sources must be reacquired for reprocessing. Deletion requires an observable
workflow and backup-expiry policy rather than a single SQL statement.
