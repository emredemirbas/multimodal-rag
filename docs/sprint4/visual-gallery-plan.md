# Retained selected-frame inspection

Date: 2026-10-26. Status: Implemented; local software and combined native workflow
verified. See `visual-gallery-validation.md`; hosted CI is checked after push.

Continue ADR 0022 with the bounded adoption/inspection part of the visual evidence
path, before indexing or public MP4 upload. No new provider, format, paid call,
raw retention or scene/OCR quality approval. Product upload remains closed.

- A private authorized command queues a separate `visual_publish` job from an
  already prepared complete result. It does not resurrect the raw input, extend
  its eligibility or invoke native tools. This command is not a public API.
- Migration 0015 only: scoped publication/job/origin links and selected-frame
  objects with immutable IDs, actual PTS, literal OCR, hashes and processing origin.
  Preserve all earlier migration bytes. Source generation advances for the new
  job; origin still points to its original extraction generation.
- Adopt one PNG per delivery, with a unique write-ahead orphan reservation and a
  post-PUT actor/lease/source fence. Reuse committed objects, not an uncommitted
  candidate. Continuations consume no failure attempt. Cancel/retry can resume
  committed derived work even after raw deletion; extraction still requires new
  upload. Reprocessing video is not silently converted into transcript indexing.
- Atomically expose the gallery only after the entire validated PNG/OCR manifest
  is retained. No partial result is public evidence. Keep source `metadata_ready`,
  no active index generation, no content_segments or new inference usage. Gallery
  preparation is not searchable `ready` or a full multimodal milestone.
- Authenticated scoped gallery JSON and bounded PNG read endpoints, no object key,
  raw video URL, credentials or private incomplete snapshot. Verify bytes/digest/
  PNG geometry and reauthorize after storage reads. Archive permits inspection;
  revoked/deleted/foreign access fails closed. Complete deletion covers all rows,
  committed objects and orphan candidates through existing prefix cleanup.
- Server-only image proxy, no-store/nosniff/same-origin headers, literal OCR and
  accessible loading/empty/error/image-error states. Label automatic unreviewed
  OCR, sampling/downscaling limitations, exact timestamps and absence of audio,
  playable video and searchable evidence. Source cards link only retained frames.
- Real PostgreSQL isolation/races/retry/continuation/manifest tests, real Celery
  process-loss and MinIO cleanup, frontend contract/proxy/render checks. Native
  OCR component evidence remains separate from fixture-backed queue tests.

Use fresh disposable services/test-only credentials; do not migrate/restart the
owner's stack or read/modify actual `.env`. Tested scoped commit/push is authorized.
Next: index retained OCR with stable frame provenance and visual citations, then
bounded authorized upload/UI and representative scene/OCR quality evaluation.
