# Local WAV transcription: staged delivery

Date: 2026-10-21
Status: Foundation implemented and locally validated; audio upload remains disabled.
See `local-asr-validation.md` for native recognition limits and the next slice.

The owner asked to push and continue after the proposed WAV/retention scope.
Push found `main` already current. Treat the continuation as approval of that
explicitly proposed scope: authorized/owned WAV, 20 MB and 10 minutes maximum,
local-only inference, original audio removed after success/cancellation/permanent
failure, retained derived transcript. Re-transcription then requires re-upload.

## Slice A: safe inference foundation (this delivery)

- Strict RIFF/WAVE validation using bounded standard-library parsing; PCM signed
  16-bit, 16 kHz, mono initially. Other WAV encodings get actionable errors. No
  FFmpeg/AV decoder is given uploaded files; validated PCM enters the model as an
  array. This narrower encoding is an implementation safety assumption surfaced
  to the owner, not permission for MP3/MP4 or arbitrary downloads.
- Application-owned transcription interface; fixed multilingual Whisper base
  via faster-whisper, CPU int8, immutable approved revision/file checksums. A
  separate explicit setup command downloads public weights, never a user request.
- Stateless private local inference service, 30-second PCM slices, one inference
  at a time, bounded request/response/timeout/tokens, no tools or prior history.
  Fail unavailable/busy/invalid output honestly; no cloud fallback or retries in
  the adapter. Unknown token counts are not invented.
- Dedicated non-root/resource-bounded container without application credentials,
  database/object access, Docker socket or user-data mounts. Model weights are
  read-only. A fail-closed inherited seccomp filter denies creation of sockets,
  socket pairs and outbound connect after the HTTP listener is created; only
  accepted inbound connections remain available. Disable core dumps and swap.
- The inference endpoint carries PCM/language only, not tenant/project IDs or
  credentials. It is not public/authenticated product ingestion. No app route,
  queue job or UI accepts audio yet. Do not call a model in the API process.
- Tests for malformed/oversized WAV, metadata bounds, strict slice contracts,
  local HTTP/error/identity/deadline behavior and the actual seccomp restriction.
  Native-model verification is separate from fake-HTTP/default CI and never
  establishes general ASR quality or timestamp accuracy.

## Slice B: durable product ingestion (follow-up, required before enabling upload)

The first private component is scoped PostgreSQL window checkpoints and complete
VTT assembly; see `asr-checkpoints-plan.md`. It does not execute ASR jobs, store
original audio or adopt/publish the returned VTT. The rest of slice B below remains
required before enabling WAV upload.

The subsequent private backend component implements the dedicated worker,
temporary-original lifecycle and VTT/indexing handoff (ADR 0019), recorded in
`media-worker-plan.md`. Authenticated upload/BFF/form and user-facing provenance/
inspection remain the final product-enablement step; current WAV uploads stay closed.

- Dedicated media queue/worker, scoped jobs and migration-backed temporary audio
  artifacts/window checkpoints with actor/lease/generation fences.
- Atomic derived transcript adoption into the existing indexing pipeline; no
  partial transcript becomes search/citation evidence. Retry saved windows under
  bounded attempts, preserve source/version provenance and zero billed usage.
- Label output as machine-generated and support inspection/correction. The base
  model's technical vocabulary is not independently verified tutorial text.
- Durable observable original-audio cleanup on every terminal path, authorization
  revocation and project/source deletion; stale workers cannot recreate audio.
  No indefinite raw-audio retention. No broad queue/volume purge.
- Authenticated bounded upload/BFF, explicit rights/language/retention controls,
  progress/retry/cancel/re-upload guidance and accessible success/error states.
- Actual queue/process-death/object-deletion tests, negative tenant/project tests,
  native owned-audio smoke and complete owned-artifact cleanup.

No binary upload capability is enabled by slice A. No original audio is retained
by the stateless service. The proposed retention is approved but not implemented
as a product workflow until slice B. No scene/OCR/vision, assignment or grading
feature is implied. Commit/push is a separate owner-authorized delivery step;
hosted CI must be verified separately.
