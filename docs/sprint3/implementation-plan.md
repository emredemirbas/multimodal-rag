# Sprint 3 implementation plan

Date: 2026-10-02
Status: Local offline-baseline delivery implemented and validated. See
`validation-record.md`; managed-provider/owner-review release gates remain open.

## Outcome and boundaries

Add source-filtered hybrid retrieval, inspected timestamp evidence and durable
project conversations with an authenticated SSE transport. Preserve the existing
transcript-first ingestion path and exact vector search; no HNSW, media pipeline,
assignment workflow or external-document fetching is introduced.

Use the existing application-owned deterministic embedding/extractive answer
providers until the owner selects a managed model/provider and its retention,
region and spend policy. No paid request or new secret is implied by this sprint.
The UI must label the extractive baseline honestly. Provider-backed quality and
the Alpha 1 release threshold require owner approval and a separately reviewed
evaluation; local fixture scores do not establish general answer quality.

## Delivery slices

1. Separately bounded PostgreSQL full-text/exact-vector candidate lists, RRF
   fusion, deterministic identifier-aware reranking, source filters and context
   diversity/size bounds. Persist retrieval/reranker/prompt versions. Reject
   citations not present in the retrieved evidence rather than trusting a model.
2. Scoped conversation/turn/citation tables in additive migration 0004. Idempotent
   message creation commits both messages, provenance and zero-cost usage
   together. Replaying a key does not append a second logical turn. Bound list,
   conversation and message counts; authorize read/write/stream and evidence.
3. Deliver validated persisted extractive answers through SSE start/delta/complete
   events. Disconnecting does not undo a committed answer. Same-key retry replays
   it; no automatic resubmission with a fresh key. This is transport streaming,
   not a claim of incremental remote model generation. Bound payloads/timeouts.
4. Accessible project chat UI: explicit questions, source selection, progress,
   stop delivery, reload/retry recovery, history and source/timestamp inspection.
   Render untrusted content as text, never active HTML. An uploaded transcript has
   timestamps but no playable video, so do not invent a video jump URL.
5. Local labelled synthetic evaluation and PostgreSQL isolation/recovery/deletion
   tests, frontend tests, Compose smoke checks and a validation record.

## Material assumptions and deletion

Each question is self-contained: history is persisted for display but is not
silently treated as evidence or sent to another provider. Follow-up contextual
reasoning awaits a selected managed provider and reviewed context policy.

All relationships and queries carry tenant and project scope. Old processing
segments remain inspectable after successful reprocessing. Source deletion also
removes turns citing that source, preventing retained extractive source text in
chat; project deletion cascades all conversations, turns and citations.

Initial local bounds: 100 conversations/project, 200 turns/conversation, 2,000
characters/question, 20 source filters, 24 candidates/channel, 4 context segments,
2 per source and 4,800 evidence characters. These are implementation safety caps,
not agreed production quotas. Managed-provider deadlines, usage/token accounting
and spend limits must be established before that capability is enabled.

## References

- [RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)
- [PostgreSQL 16 text search](https://www.postgresql.org/docs/16/textsearch-controls.html)
- [FastAPI streaming response](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
