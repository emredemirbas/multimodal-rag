# Optional local answer-generation slice

Date: 2026-10-11
Status: Implemented; final real-model verification is recorded in
`local-model-validation.md` (ADR 0015).

- Default extractive demo/CI stays keyless and does not download a model.
- Optional non-root, resource-bounded Ollama serves local Qwen3 4B only;
  disable cloud functionality and keep the model port unpublished.
- Explicit setup downloads model weights once; API questions never pull weights.
- Structured output, no tools/history/secrets, bounded local-only HTTP,
  no redirects/proxies/retries/cloud fallback, and a one-call API capacity gate.
- Persist model/prompt version, manifest lookup and returned token counts;
  zero billed API cost, not a claim of free hardware/electricity.
- Keep 64-D hash/lexical retrieval compatible with existing data and label it.
  Real semantic embeddings are a separate data migration.
- Weak lexical matches abstain before inference; attribute them to the application
  evidence policy rather than claiming the model produced that result.
- Unload after each generation to bound idle RAM/transient prompt retention.
- Show configured answer mode and honest unavailable/busy recovery. Retain
  source-deletion and project-authorization fences after generation.
- Test fake HTTP failures/invalid citations, token persistence, scope and a
  separately reported real-model smoke. Keep weights in a Docker volume.

This does not add media/ASR/vision or assignment features or certify production.
