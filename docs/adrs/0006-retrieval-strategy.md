# ADR 0006: Project-filtered full-text and exact vector retrieval

- Status: Accepted
- Date: 2026-09-21

## Context

Programming questions contain exact identifiers as well as semantic concepts.
Approximate indexes can reduce recall and complicate filters at small scale.

## Decision

Combine PostgreSQL full-text search with exact pgvector similarity under tenant
and project filters, then fuse and rerank results. Do not create HNSW until a
representative benchmark demonstrates a latency need and acceptable filtered
recall.

## Consequences

The baseline is predictable and isolation is explicit. Retrieval latency must be
remeasured as project corpora grow.
