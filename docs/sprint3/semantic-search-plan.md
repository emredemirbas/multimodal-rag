# Free local semantic retrieval slice

Date: 2026-10-12
Status: Implemented and locally validated; see `semantic-search-validation.md`.
Earlier RAG follow-up, not assignment/media work.

ADR 0017 and `resumable-indexing-validation.md` supersede the initial one-delivery
128-chunk limit below; this record preserves the original semantic slice's scope.

The owner authorized continued development and removal of their test data.
Keep the keyless hash demo as the default. Explicitly opt into the existing private
Ollama service with multilingual Qwen3 Embedding 0.6B (639 MB, 1024 dimensions).
No paid API, external prompt delivery, automatic model pull or cloud fallback.

Material assumptions:

- Pin the approved model manifest, dimensions and query-instruction version as an
  immutable vector-space ID. Check the local manifest before and after each call.
- Migration 0007 preserves old 64-D segments and citations. Exact search filters
  tenant, project, active generation, source and vector space **before** distance
  calculation. Changing modes requires explicit source reprocessing, never mixing
  lexical candidates from an incompatible generation into a semantic answer.
- Real document embeddings run in the durable ingestion worker, in batches of
  eight. Cap this experimental CPU path at 128 chunks and 70 seconds per attempt;
  failures retain the previous generation and existing bounded retry semantics.
  The legacy synchronous ingestion endpoint is unavailable in semantic mode.
- Query embedding has a six-second inference deadline. Local generation uses a
  shared 28-second retrieval/answer budget to fit the existing 30-second web boundary;
  answer inference uses remaining time, capped at 24 seconds (see validation).
- Semantic relevance uses raw cosine, not RRF scores. Start with a conservative
  experimental 0.40 floor, measured on explicit English/Turkish paraphrase and
  unsupported fixtures; this is not a calibrated probability or faithfulness proof.
  Keep the default hash mode's lexical gate unchanged. Preserve authoritative
  citation validation and abstention. Model reasoning can still be wrong.
- Record space/model/digest/query usage and processing usage; unknown token counts
  remain null and billed API cost remains zero. UI shows mode and reindex warnings.

Verify fake HTTP malformed vectors/manifests/timeouts/no redirects, bounded batches,
mixed-space database isolation, migration preservation, successful/failed reindex,
old citation stability, deletion, UI states, all offline regression suites, and a
separate real-model/real-worker smoke. CI must not download model weights.

References: [official model](https://ollama.com/library/qwen3-embedding:0.6b),
[Qwen model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B),
[native embedding API](https://docs.ollama.com/api/embed).
