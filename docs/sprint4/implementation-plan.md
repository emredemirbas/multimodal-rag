# Sprint 4 — ordered authorized-transcript playlist slice

Date: 2026-10-11
Status: Ordered-transcript slice implemented and locally validated; full
multimodal/Alpha 2 remains open. The dependency-audit blocker is resolved by the
tested pinned lint adapter; hosted CI still requires a push. See
`validation-record.md`.

## Scope and material assumptions

The owner asked to continue after committing the Sprint 3 local baseline. Start
Sprint 4 with ordered playlist relationships and independently recoverable
authorized subtitle processing. The managed LLM/ASR/vision provider, binary input
limits and temporary media retention remain open. The owner subsequently chose
zero-service-spend portfolio mode: optional local Ollama answers are added as a
follow-up to the earlier RAG slice (ADR 0015), not binary media. Do not enable media,
download videos/captions, or make paid model calls without those decisions.

YouTube metadata continues through the existing official, allowlisted adapter and
requires a server-side Data API key. Tests use synthetic responses; live provider
availability is not inferred from fixtures. Every transcript needs its own rights
assertion. The user explicitly selects the playlist video it represents; the
application records that assertion, not a verified audiovisual alignment.

## Delivery

- Add immutable ordered metadata snapshots with provider playlist-item identity,
  video identity and metadata generation. Preserve the last successful snapshot
  on a failed refresh. Carry transcript relationships to a refreshed item only
  when both provider item and video identities still match.
- Atomically associate an authorized upload and its queued job with a scoped
  playlist item. Include the item in the upload idempotency hash. Replacing a
  transcript requires the previous job to be terminal; the previous independent
  source and its evidence are not silently deleted.
- Fence worker claims under the project lock, with a default maximum of two
  active transcript jobs per playlist (configurable 1–4). Waiting for a slot does
  not consume a processing attempt. Requeue waiting jobs through the durable
  outbox. Existing retry/cancel/lease recovery remains per video.
- Show ordered items, explicit truncation, missing transcripts, per-video state,
  partial failure and independent retry controls. Keep source controls and polling
  accessible and stop polling hidden/terminal views.
- Preserve tenant/project scope, prior citations and source/project deletion.
  Removing playlist metadata unlinks but does not delete independently uploaded
  transcripts; the named confirmation must explain that behavior.
- Test migration upgrades, authorization, ordering/refresh, concurrent slot claims,
  idempotency, partial failure/resume, deletion and web contracts/states.

## Remaining Sprint 4 work

FFmpeg/media isolation, scene detection, frame deduplication, OCR/vision models,
transcript/frame alignment, visual citations and the visual benchmark remain
unimplemented. Provider-backed Alpha 1 gates also remain open. Do not call this
slice full Sprint 4 or Alpha 2 completion.
