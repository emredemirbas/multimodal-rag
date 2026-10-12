# ADR 0015: Free local portfolio mode

- Status: Accepted by the owner's explicit direction
- Date: 2026-10-11

## Context and decision

The owner clarified that this is a GitHub portfolio project, not a production
service, and delegated provider choices with no out-of-pocket API/service spend.
This supersedes the required managed-model strategy and the current private-beta
launch goal. Keep the broader learning-workspace roadmap as a demonstration
roadmap; do not imply production readiness or invited-user deployment.

Default startup remains the reproducible, keyless extractive demo. Add an explicit
optional local Ollama profile, with Qwen3 4B as the initial answer model. This fits
the observed 16 GiB development machine better than a large model. It still uses
disk/RAM/CPU and has variable latency; “no service bill” does not mean no local
resource/electricity use. Model downloads are explicit, never triggered by user
questions or ordinary default startup. The service has no cloud fallback or API
keys; model calls are allowed only to loopback/the local Compose service. Compose
does not publish the model port; it stays behind the authenticated application.

Start with local answer generation, retaining the current deterministic 64-D
embedding/lexical retrieval infrastructure rather than silently mixing incompatible
semantic embeddings with existing data. Label this retrieval limitation. Native
semantic embeddings and local ASR/OCR remain follow-up slices, not features
claimed by this adapter.

Require at least 50% meaningful query-term overlap before local generation while
using hash retrieval. Weak/empty matches abstain without a model call and are
attributed to `local-evidence-policy`/`lexical-abstention-v1`, with zero tokens and
no model manifest. This conservative guard rejects some legitimate paraphrases;
it is not a learned relevance or faithfulness classifier.

Structured model answers are limited to retrieved evidence IDs; keep citation
ownership and generation validation, explicit abstention, bounded requests,
local model/prompt/token attribution and zero billed API cost. Unknown usage stays
null. Do not give the model tools, credentials, filesystem/network access, or
implicit conversation history. A configured but unavailable model fails honestly
instead of silently switching to a different answer provider.

Constrain model citation strings to retrieved IDs in the request schema and still
validate them server-side. Unload the model after each generation (`keep_alive=0`)
to limit transient prompt/KV retention and idle RAM usage. No training or prompt
artifact is written to the model volume; it contains reusable public weights.

Privacy remains local: uploaded transcripts, chat and derived evidence stay in
local stores until deletion. No prompt is sent to a managed model service. The
existing rights checks, project isolation, complete deletion and hardened future
submission-runner boundary remain unchanged. Binary input retention/limits and
code execution do not become authorized just because providers are local.

References: [official local Docker setup](https://docs.ollama.com/docker),
[native structured chat API](https://docs.ollama.com/api/chat),
[Qwen3 4B model and license](https://ollama.com/library/qwen3:4b).
