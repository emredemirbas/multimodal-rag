# Opt-in authorized MP4 upload

Date: 2026-10-27. Status: Implemented; local software/native/boundary verification
recorded in `video-upload-validation.md`. ADR 0026. Hosted CI is checked after push.

Connect only ADRs 0021–0025's accepted local selected-frame/OCR pipeline. Keep
`VIDEO_UPLOAD_ENABLED=false`, standalone uploads only, no paid fallback or model
download. No user `.env`, services or database migration state will be changed.

Material assumptions: use a separate video capability endpoint so the existing
WAV capability contract remains unchanged. Availability is configuration, not
native-service readiness or OCR quality. Accept explicit en/tr/experimental en+tr,
rights and permitted-frame/OCR retention acknowledgement. MP4 remains <=100 MB,
600 seconds, H.264/avc1/yuv420p <=1080p/60fps, <=20 selected frames; optional AAC
is ignored. Do not infer a playlist association or provide a video/audio player.

- Authenticate/gate before consuming API bodies; bound actual wire bytes to
  100,000,000 + 16,384 and unfinished reads to 30 seconds. Preserve subtitle/chat/
  WAV limits. Bound concurrent video deliveries to one per process (API and BFF),
  rejecting excess rather than queuing large bodies; this is not a global quota.
  Bound BFF multipart markers before parsing to prevent unbounded small-part
  allocation. API tmpfs grows from 64 to 256 MiB so one 100 MB spooled upload fits;
  this does not expand any other request limit or original-object retention.
- Same-origin server-only BFF validates UUID, capability, wire/form fields, type,
  filename, bytes, rights/language/ack and scoped original-job receipt. No parser,
  storage key, server credential or raw upstream error enters the browser.
- Registration always opts into the existing atomic three-stage workflow. No
  native inference in API/BFF and no new schema; use existing job/cleanup state.
- A stopped/uncertain browser delivery is not job cancellation. Preserve unchanged
  file/fields/request key until a validated receipt; refresh current source stages.
- Typed source inventory projects original-video processing expiry, retirement,
  pending/failed cleanup and confirmed deletion from full scoped input/cleanup
  records, not mutable source metadata. Continue polling cleanup after jobs finish.
  Permit original-initiator cleanup retry using the existing scoped action.
- Accessible default-off/unavailable, consent, loading, success, recovery and raw
  cleanup states. Explain unreviewed/limited OCR, no audio understanding, uniform
  sampling/quality limits and re-upload after original retirement. Derived retry
  does not perform native inference again; public video reprocess stays closed.
- Test API/BFF actual-byte, malformed/duplicate fields, timeout/disconnect,
  concurrency, auth/project/tenant and receipt fences; retain all old regressions.
  Verify native authored MP4 through actual public API/BFF/production UI, atomic
  jobs, citations and complete deletion on a fresh disposable stack. Include a
  near-limit request in isolated verification, not a broad new media allowance.
