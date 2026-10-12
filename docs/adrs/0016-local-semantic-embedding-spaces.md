# ADR 0016: Free local semantic retrieval with immutable vector spaces

- Status: Accepted for the owner-authorized portfolio follow-up
- Date: 2026-10-12

Keep hash/extractive as the keyless default. Optional local Ollama serves approved
Qwen3 Embedding 0.6B, 1024-D, Apache-2.0 multilingual weights (639 MB). Use an
English versioned instruction for queries and raw transcript text for documents.
No cloud/paid fallback, model pull during requests, redirect, proxy or arbitrary
network destination. The existing private/resource-bounded service is reused.

Pin the manifest `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`.
Space identity includes this digest, dimensions and query-template version. Validate
the tag before and after every batch/query; do not label output with a cached tag.
The local model administrator is trusted; arbitrary concurrent model replacement
is unsupported. A changed manifest requires an explicit new space/migration and
reprocessing, not accepting new weights into the existing index.

Migration 0007 widens the vector column without deleting/recomputing evidence.
Writes enforce one of the known space/dimension pairs. Both retrieval channels
use a MATERIALIZED scope/active-generation/space/dimension filter before cosine.
Use exact pgvector search and full-text candidates, RRF bookkeeping plus cosine
and a small identifier boost; no ANN/learned reranker is added. Old generations
remain inspectable. UI excludes incompatible sources and requests explicit
reprocess (fresh upload for legacy validation-only sources). Failure preserves
previous evidence; the existing job/deletion/authorization fences are unchanged.

Document embeddings run in real jobs, eight chunks/batch, 128 chunks/input and a
70-second attempt budget under existing task limits/leases/retries. Recheck the
claim between batches and before atomic activation. No partial index is activated.
Queries have six-second inference, one-second manifest checks. Local answers use
the remaining shared 28-second retrieval/answer budget, with inference capped at
24 seconds, to fit the existing 30-second BFF boundary. A 16-second fixed cap
proved too short for cold CPU model loading in native verification.
The legacy synchronous ingest endpoint is unavailable in semantic mode. Unknown
tokens remain null; actual processing/query tokens, digest and space are persisted
separately from answer usage with zero billed API cost. Stage/latency logging never
includes input text, credentials or vector payloads. Unload weights after each call.

Keep the hash-mode 50% lexical gate. Semantic mode uses raw cosine >= 0.40, never
fused scores, as an experimental relevance screen. This supports some paraphrases
without pretending cosine establishes faithfulness. Related unsupported questions
and valid false negatives remain possible; authoritative citations and model
abstention still apply. Record small fixtures, limitations and actual local results,
not broad multilingual or production-quality claims. No media/assignment scope.

References: [official Ollama model](https://ollama.com/library/qwen3-embedding:0.6b),
[Qwen model card/license/instructions](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B),
[native batch embedding API](https://docs.ollama.com/api/embed).
