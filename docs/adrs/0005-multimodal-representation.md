# ADR 0005: Text-aligned multimodal representation

- Status: Accepted
- Date: 2026-09-21

## Context

Slides, terminals, code, and diagrams contain evidence not present in speech. A
separate visual-vector stack would increase Sprint 0 complexity before a baseline
exists.

## Decision

Represent selected frames through OCR and structured descriptions aligned to a
timestamp. Index that text in the hybrid retrieval pipeline and retain a stable
frame reference when storage is permitted. Evaluate native image embeddings only
against this baseline.

## Consequences

Visual evidence participates in retrieval immediately. Some pixel-level detail
may be lost, so visual-only benchmark results determine whether a second index is
warranted.
