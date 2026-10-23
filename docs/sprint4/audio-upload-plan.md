# Opt-in authorized WAV upload boundary

Date: 2026-10-23
Status: Implemented; local software/native workflow gates pass. The feature remains
off by default; see `audio-upload-validation.md` for evidence and quality limits.

Continue the accepted ADR 0018/0019 WAV scope, not compressed media, video/OCR,
new providers or assignments. The owner authorizes tested scoped commit/push.

Assumption surfaced in chat: expose this as an experimental, explicit local opt-in
(`AUDIO_UPLOAD_ENABLED=false` by default), after installing the pinned public
weights and starting `local-asr`. No automatic model download, paid fallback or
change to the user's actual `.env`/running services. A capability reports configured
availability, not model health or an accuracy certification. The earlier native
technical-vocabulary failure remains documented.

- Separate authenticated multipart WAV API and same-origin browser BFF route.
  Do not raise the existing subtitle Server Action limit or the chat body limit.
  Bound audio wire bytes before multipart parsing, including chunked uploads;
  reject disabled/unauthenticated audio before consuming the API body. Bound the
  BFF stream before parsing, reject duplicate/extra fields and enforce safe IDs,
  rights, language, filename/type and byte count. Validate actual RIFF/PCM/duration
  again through the existing repository, never a native decoder in the API.
- Rights assertion and auto/en/tr language, stable idempotency across uncertain
  delivery, explicit temporary-original/one-hour eligibility/cleanup guidance.
  Browser cancellation or timeout is not a guarantee that registration rolled back.
  Return only a validated scoped receipt through the BFF; server credentials and
  internal storage/model details never enter the browser.
- Call the existing durable media repository/queue, not inline inference. Preserve
  actor/project/tenant fences, orphan reservations, retries/cancel, raw retirement,
  VTT adoption/index activation and complete deletion. No schema change is needed.
- Accessible gated form, loading/error/success/cancel-delivery and re-upload states;
  existing source/evidence/transcript/chat provenance and cleanup UI stay in use.
  Default and unavailable-capability states must remain honest and fail closed.
- Test API auth/scope/disabled/body bounds/invalid WAV/rights/idempotency and queue
  handoff; BFF origin/stream bounds/protocol validation, UI recovery and existing
  subtitle/chat regressions. Use isolated disposable infrastructure for broad tests.
- Separately verify implementation-authored synthetic speech through the actual
  private native model, media/index queues, API/BFF/production UI and confirmed raw
  cleanup, then source/project deletion. Use a new disposable Compose project,
  test-only credentials and ports, and only the preinstalled public model volume
  read-only. Never attach app volumes or reset/purge the user's state. Report this
  as native pipeline evidence, not human speech, technical vocabulary, multilingual
  or timestamp-accuracy approval; define any keyword diagnostic before running it.

Native diagnostic fixed before execution: synthesize the implementation-authored
English phrase “Hello. This is a local audio transcription test. The application
has a health check.” with the installed FFmpeg flite filter, then export canonical
16 kHz mono signed-16 PCM WAV in memory. Separately report whether the resulting
text contains `hello`, `audio` and `health` (case-insensitive); a mismatch is a
failed keyword diagnostic, not grounds to change the expected words or hide the
earlier `endpoint` failure. A second 600-second silent WAV tests the large browser
upload boundary, but must be cancelled before starting the isolated media worker.

If native verification cannot complete safely, leave the public opt-in gate closed
and document the missing evidence instead of treating fixture inference as native.
