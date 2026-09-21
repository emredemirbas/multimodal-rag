# ADR 0007: Application-owned model-provider boundary

- Status: Accepted
- Date: 2026-09-21

## Context

Embedding, transcription, vision, and generation providers vary in price,
quality, retention, and availability. Provider payloads should not define domain
objects.

## Decision

All model calls use application-owned interfaces and record provider, model,
prompt or processing version, latency, usage, and attributable cost. Sprint 0
ships deterministic local providers so tests and the demo require no credentials.

## Consequences

Provider replacement is localized and tests are reproducible. Production quality
must be established with provider-backed evaluation rather than inferred from the
offline baseline.
