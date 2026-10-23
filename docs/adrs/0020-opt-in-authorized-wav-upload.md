# ADR 0020: Experimental opt-in authorized WAV upload

- Status: Accepted continuation of ADRs 0018/0019; default remains disabled
- Date: 2026-10-23

Expose the existing durable local media workflow through a separate authenticated
multipart endpoint and same-origin browser Route Handler. Do not expand the
subtitle Server Action's 2 MB limit or chat's 16 KiB wire limit. WAV remains
20,000,000 bytes / 600 seconds / signed-16 PCM / 16 kHz / mono; multipart wire
allowance is 16,384 additional bytes. Count actual streamed bytes before parsing,
including chunked/false-length input, and bound unfinished audio reads to 30 seconds.
The API authenticates and checks the opt-in flag before reading the audio body.
The browser boundary checks Origin/Host, bounds bytes, rejects duplicate/unknown
fields and forwards only verified inputs with server-only credentials. The API's
stdlib RIFF validator remains authoritative; never decode uploaded media natively
in the API, BFF or ordinary worker.

`AUDIO_UPLOAD_ENABLED=false` is the default. Authenticated
`GET /api/v1/ingestion/capabilities` reports the configured flag, available
repository and fixed limits, not model readiness or accuracy. Failed/malformed
capability checks hide the form and reject BFF writes. The operator must explicitly
install the pinned weights and start `local-asr` plus its media worker before opting
in. Ordinary startup/CI does not fetch weights or invoke paid/cloud providers.
This change does not modify the owner's local `.env` or restart their services.

Require one file, a rights assertion, auto/en/tr language, a stable request key
and `retention_acknowledged=accepted`. Explain the one-hour eligibility including
queue waiting, tracked deletion versus expiry, retained derived transcript, and
new-upload requirement after original retirement. A stopped/timeout browser
delivery is not a job cancellation or a rollback guarantee: preserve the unchanged
draft/key until a validated scoped receipt confirms acceptance. Registration
idempotency uses the existing persisted command boundary; no new retention or
database schema is introduced. Source processing, retries/cancellation, usage,
provenance and full deletion continue through ADR 0019's scoped repositories/jobs.

Automatic text and timestamps remain unreviewed. Native workflow verification and
synthetic keyword diagnostics are separate evidence, never representative speech/
technical/multilingual quality certification. Retain the earlier failed `endpoint`
diagnostic. MP3/MP4, video/frame retention, arbitrary downloading and vision/OCR
remain outside this slice. See `../sprint4/audio-upload-plan.md` and its validation
record for the verification/enablement gate.
