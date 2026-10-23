# Experimental authorized WAV upload validation

Date: 2026-10-23
Status: API/BFF/form implemented; local software and native pipeline gates passed.
Default remains **`AUDIO_UPLOAD_ENABLED=false`**. Explicit local setup/opt-in, not
automatic rollout, general speech-quality approval or full multimodal completion.

## Delivered

- Authenticated, no-store capability with fixed limits; configuration availability,
  not model readiness. Experimental multipart WAV API delegates to the existing
  scoped media repository/ASR queue. No inference runs inside the request.
- API authenticates/checks the flag before consuming audio. Actual bytes and slow
  reads are bounded before multipart parsing, including chunked/false-length
  requests. File limit 20,000,000 bytes; wire allowance 16,384 extra bytes; 30-second
  read bound. Actual RIFF/PCM/600-second validation remains stdlib-only. No subtitle
  or chat limit increase, media decoder, new provider or schema change.
- Separate same-origin Next.js Route Handler checks Origin/Host, capability,
  actual stream size/time, exactly five fields, rights/language/consent, type/name
  and upstream project/source/job identities. Only a scoped minimal receipt reaches
  the browser. Server credentials, raw parser/provider errors and storage keys do
  not. It uses no-store and safe owned error messages.
- Accessible form with explicit rights, auto/en/tr language, temporary-retention
  consent, limits and unreviewed-text caveats. Preserve the unchanged draft/key on
  uncertain delivery; reset only after verified acceptance. Stop-delivery does not
  claim job cancellation. Separate refresh-failure messaging avoids treating an
  accepted registration as failed. Off/unavailable/archived states hide the form.
- Existing per-version provenance, media/index continuation/retries, one-hour
  eligibility, tracked original cleanup, retained VTT reindex and full source/
  project deletion remain authoritative. No original playback/download is added.

## Software checks

- Full backend against three newly created disposable PG/Redis/MinIO services,
  test-only allowlisted credentials/DSNs and `TEST_REAL_WORKER=1`: **268 passed,
  no skips** (80.87 seconds). Earlier iterations passed **264**, then **267** tests;
  the final run includes explicit same-tenant cross-project command/receipt isolation.
  No application `.env`, mounts, volumes, buckets or queues are used. Exact newly
  created container IDs and tmpfs data are cleaned afterwards.
- New API tests cover pre-read auth/disabled rejection, chunked wire overflow and
  timeout, unchanged subtitle/chat limits, actual WAV byte/duration/encoding errors,
  rights/language/consent/key/extra/duplicate fields, tenant/project/archive scope,
  queued-not-inline processing, idempotency/conflict, VTT/index provenance,
  cancellation/re-upload and original/source cleanup.
- Frontend **22 files / 98 tests**, lint and typecheck pass on local Node 20.19.6
  and CI-pinned **Node 24.21.0**. The latter runs in a network-disabled ephemeral
  builder container without app credentials/data mounts, with all **5** actual
  lint-adapter compatibility tests. New BFF/form tests cover origin, fail-closed
  capability, byte/time bounds, strict scoped receipts, unknown/duplicate fields,
  safe errors, retained keys/drafts after uncertainty, stop-delivery, acceptance/
  deduplication/reset, failed refresh and archived/off states.
- Full `npm audit --audit-level=moderate`: **zero vulnerabilities**. The initial
  sandbox audit could not resolve npm's host; the normal network-enabled retry
  completed successfully, not an ignored advisory or suppressed check.
- Production Docker builds pass for API, migration/scheduler, ingestion, media,
  frontend (Next.js 16.4.2 / Node 24.21.0) and isolated ASR. Full deployment/native
  verification below uses those images. Migrations 0001–0012 remain unchanged.

## Native workflow, separately from recognition quality

The verification driver created a unique disposable Compose project, validated the
resolved configuration before startup, supplied test-only credentials through an
allowlisted environment and `--env-file /dev/null`, and used new data volumes,
networks and loopback-random API/frontend ports. Only the already installed public
ASR weight volume was shared **read-only**. ASR had no published port or application
credentials, retained its internal-only network/kernel/resource restrictions, and
was a new test container, not the user's running model service. No weight download,
paid API, app deployment, migration reset or shared-data cleanup occurred.

1. Production SSR shows the experimental form; a foreign-Origin browser upload is
   rejected without creating a source. A canonical **19,200,044-byte / 600-second
   silent WAV** crosses the actual BFF/API, proving the dedicated route is not
   constrained by the unchanged 2 MB Server Action limit. Cancel it before starting
   the test media worker; confirm the cleanup marker and an empty MinIO source
   prefix, without running twenty silence windows through the model.
2. Generate owned synthetic speech entirely in memory using installed FFmpeg flite
   (`slt`) and the phrase fixed in `audio-upload-plan.md`: “Hello. This is a local
   audio transcription test. The application has a health check.” Wrap raw signed
   PCM in a canonical WAV: **176,204 bytes**, 88,080 frames (5.505 seconds). This
   trusted fixture generator is not an uploaded-media decoder in the product.
3. Upload through the production same-origin BFF with explicit rights/language/
   consent/key. Actual private Whisper-base inference and real Celery media/index
   workers produce retained VTT and published evidence. Source, transcript and
   evidence production SSR identify it as not human-reviewed; typed origin points
   to the actual original ASR job. The raw cleanup marker is confirmed and MinIO
   contains derived artifacts, but no original `input.wav`.
4. Replay the same request: the same source/original ASR receipt is returned, even
   after conversion to a transcript. Reindex retained VTT into generation 2 after
   raw deletion: the original ASR origin and generation-1 evidence remain stable.
5. Delete the owned source, await tracked cleanup and assert missing transcript plus
   empty source object prefix; delete the owned project, await cleanup and assert
   404 plus empty project prefix. Finally remove only the unique test project's
   containers/networks/data volumes; preserve its explicitly external public
   weights and all pre-existing application services/data.

The first native-driver attempt stopped because its generic wait helper treated
the deliberately cancelled large-upload source as unexpected before cleanup could
finish. This was a probe assertion error, not an ASR/product failure or a successful
end-to-end result. Its own project/stack was cleaned. Allow the expected cancelled
state while awaiting the separate deletion marker and rerun in a fresh stack;
the complete sequence above then passed. The temporary verification drivers/overlay
are not runtime dependencies or app Docker-socket access.

Fixed-before-inference synthetic keyword diagnostic: **PASS**, `hello`, `audio`
and `health` all present (case-insensitive). Do not tune expectations to the output
or present this tiny synthetic voice as representative accuracy. The earlier
failed `endpoint`/`end point` diagnostic in `local-asr-validation.md` remains
unresolved. No reviewed natural English/Turkish speech, noise, code identifiers,
long-input native transcription or human timestamp accuracy has been established.
The 600-second input above checks upload/cancellation, not long-ASR quality or
performance. Existing all-silent/continuation/process-loss behavior uses controlled
fixtures; do not relabel it as native recognition evidence.

## Operation and remaining scope

README documents explicit weight setup, `local-asr`/media-worker startup, opt-in,
form use, uncertain delivery and opt-out. The actual local `.env` remains unchanged,
ignored and mode 0600; existing application services are not restarted. Do not copy
the example over local credentials. No API schema/SQL migration rewrite, bucket
purge or user source deletion. Hosted CI for this change must be checked separately
after push; the previous security corrective commit passed run `39959500922`.

Vision/OCR/video/frames and reviewed speech quality remain open. Assignment,
external-document and grading decisions remain later-sprint work. The new WAV path
is experimental opt-in, not Sprint 4/Alpha 2 completion or production readiness.
