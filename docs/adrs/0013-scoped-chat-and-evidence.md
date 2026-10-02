# ADR 0013: Scoped chat, immutable evidence and validated SSE delivery

- Status: Accepted for the authorized local Sprint 3 infrastructure slice
- Date: 2026-10-02

## Decision

Retrieve up to 24 full-text and 24 exact-vector candidates under the same
tenant/project/active-generation/source filters. PostgreSQL `simple` text search
uses bounded normalized OR terms to retain programming identifiers. Fuse unique
segments with RRF (k=60), then deterministically rerank by query-term coverage.
Build at most four context segments, two per source and 4,800 characters. This
is a reproducible heuristic baseline, not a learned reranker or general semantic
quality guarantee. HNSW is not introduced.

The extractive provider quotes up to two segments with at least 50% query-term
overlap or abstains. Model output cannot cite a segment merely because it belongs
to the project: its complete evidence record must match a retrieved snapshot.
Providers receive deep copies and cannot mutate the authoritative snapshot.
Record retrieval/reranker/prompt versions, provider/model and source generation.

Conversations and immutable turns carry both scopes, an authenticated actor,
idempotency key/hash, chronological sequence and authoritative citation FKs. A
turn contains its user question, assistant response and zero-billed local usage;
unknown token counts are null rather than fabricated. Turn, citations and
retrieval attribution commit together under the project lock. Concurrent same-key
requests create one logical turn/run. Different input with the key returns 409.
There is no external provider call whose cost could be duplicated in this slice.

Bound the local baseline to 100 conversations/project, 200 retained turns per
conversation, 2,000 characters/question, 20 source IDs and 16 KiB JSON wire bodies.
Project archive prevents new conversations/turns but permits history/replay.
History is displayed, not implicitly sent to a model or used as tutorial evidence.
These caps are not production quota commitments.

POST message delivery uses SSE start/delta/complete events after validated durable
commit. A disconnected client may reload history or replay the same request key.
“Stop delivery” does not claim to cancel an already committed generation. Recheck
project/turn/membership existence between chunks; deletion stops subsequent
delivery. No tools, credentials or external-document fetching are supplied to the
answer provider. SSE is transport streaming, not incremental remote generation.

Next.js keeps the bearer token server-side. Mutating chat proxies require JSON,
bounded streamed bodies and the browser-facing Host/Origin match. The standalone
server's internal request URL is not the public origin. Do not accept arbitrary
forwarded host headers to bypass this guard. The proxy and browser have 30-second
delivery deadlines; history reads have bounded deadlines. Local development still
uses the existing loopback-only single-user identity, not a hosted login system.

Citation inspection is scoped but not restricted to the current active generation:
old segment content/timestamps remain stable after reprocessing. Uploads do not
provide a video player; the UI shows precise transcript timestamps rather than an
invented playback URL. A source-delete trigger removes turns citing that source,
including the quoted derived answer text. Project deletion cascades chat and
retrieval data. Minimal cleanup/audit records retain no chat or source text.

## Release boundary

No managed model/vendor, retention/region policy or paid request was selected.
Keep the extractive baseline explicitly labelled in the UI. A 19-question
synthetic, implementation-authored regression set supplies initial labels, not
independent human-reviewed quality evidence. Alpha 1 still requires owner-reviewed
material, an agreed quality threshold and provider-backed evaluation. Later media,
LangGraph tutoring, assignments and grading are not added by this decision.

References: [RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf),
[PostgreSQL 16 text search](https://www.postgresql.org/docs/16/textsearch-controls.html),
[FastAPI streaming response](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse).
