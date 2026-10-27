# Retained OCR indexing and frame-backed citations

Date: 2026-10-27. Status: Implemented; local software and native workflow verified.
ADR 0024; see `visual-index-validation.md`. Hosted CI is checked after push.

Continue only the accepted retained selected-frame/OCR path. No public MP4 upload,
native re-extraction, original retention extension, paid provider, descriptions,
scene detector or quality approval. The owner authorizes tested scoped push.

- Internal authorized `index_visual` command pins one complete gallery and the
  configured immutable embedding space in a new generation. Separate ordinary
  ingestion task, not native decoding or an API background task. Existing private
  video registration/publication remain explicit steps.
- Deterministic 1,200-code-point literal slices per frame, at most 280 chunks.
  Whitespace-only slices are omitted. Each segment retains frame ID, slice offset,
  actual PTS and an immutable processing version. A frame is a point observation:
  start=end=actual PTS, not an invented visible-duration interval.
- Hash and approved local Qwen embeddings use batches of eight, private scoped
  checkpoints and bounded continuations. No partial evidence; complete validated
  promotion atomically activates search and records accepted embedding usage once.
  An entirely blank gallery fails honestly, without changing earlier evidence.
- Add migration 0016 only. Full scoped job/gallery/frame/version relationships,
  actor/membership/source/token/wall-clock fences, saved-batch validation and
  deletion cascades. Retry reuses committed work; a new internal command creates
  a new index generation without raw/native access. Public video reprocess stays
  closed until the later product workflow; derived index retry is supported.
- Retrieval, stateless answers, persisted chat/history and evidence inspection
  project the indexed generation's original visual origin, never mutable source
  metadata. Show unreviewed OCR and link the stable frame through existing protected
  gallery/PNG reads. No vision-model claim or fabricated playback URL.
- Gallery availability and current index state are separate. Show actual active
  index generation/space; incompatibility with configured search is explicit.
- Verify isolation, stale/expired/revoked writes, corruption, continuation/retry,
  atomic publication, stable old citations, full deletion, real worker recovery,
  frontend contracts/states and a separately reported native production workflow.
  Use disposable services/test credentials, not actual `.env` or user app data.
