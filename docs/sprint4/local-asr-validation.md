# Local WAV ASR foundation validation

Date: 2026-10-21
Status: Restricted inference foundation validated; **product audio upload remains
disabled**. No general ASR quality or full multimodal completion is claimed.

## Delivered boundary

- Strict bounded RIFF/WAVE inspection, signed 16-bit PCM/16 kHz/mono, 20 MB and
  10-minute input limits, 64 metadata chunks, exact <=30s PCM slices. No native
  decoder receives uploaded files, and metadata is never interpreted as XML/URLs.
- Application-owned local-only transcription interface with immutable base-model
  revision, engine/decoding profile and four file hashes. Explicit atomic public
  weight setup, checked redirects/sizes/checksums, no existing-weight overwrite.
- Optional credential-free private ASR container, no published port, read-only
  root/weights, no user-data/Docker-socket mounts, two CPU cores, 2 GiB RAM/no swap,
  64 PIDs, 32 MiB tmpfs, dropped capabilities and no-new-privileges.
- Actual inherited seccomp denial of new sockets/socket pairs/outbound connect
  after listener binding. Missing kernel isolation or model files fails closed.
- Fresh filtered model subprocess per window, clean allowlisted environment,
  35s wall/30s soft CPU limits, bounded anonymous tmpfs output, no core dumps. PCM
  stays in memory/stdin; no original audio is persisted by the model boundary.
- Validated relative timestamps, input counts/languages/profile, 32 KiB output,
  256 generated-token bound and bounded concurrent requests. Empty speech is a
  valid slice; overlapping/out-of-window or malformed evidence is rejected.
- Content-free method/route/status and inference count/duration/profile logs.
  Raw model errors, recognized text, PCM, application IDs and secrets are absent.
  No token counts, project attribution or billing events are fabricated.

## Automated verification

- Full backend with PostgreSQL/Redis/MinIO and isolated actual worker probes:
  **186 passed, no skips** (final run: 63.77s). New tests cover malformed/duplicate/truncated/oversized
  WAV, exact maximum duration, PCM boundaries, unknown encodings, strict output,
  local URL/no-proxy/no-redirect behavior, busy/timeouts, setup/hash/adoption and
  provider environment/child deadline behavior. Existing isolation and deletion
  regressions remain intact.
- Actual kernel probe runs in its own process: new IPv4/IPv6/Unix sockets, socket
  pairs and sockets in a child fail, while a pre-bound listener still accepts and
  serves an inbound connection. The parent pytest/application process is unchanged.
- Optional production image builds successfully and its dependency compatibility
  check passes. The actual non-root Docker container also passes the seccomp probe.
- Frontend regression: **17 files / 60 tests**, lint and typecheck pass. No audio
  form or application upload route was added. No schema/migration was needed for
  this stateless slice; existing SRT/VTT limits/data are unchanged.
- Compose configuration/diff checks pass. CI now builds the optional image and
  checks kernel isolation without downloading Whisper weights. The hosted CI
  result for this slice has not yet been verified; local checks are not a hosted
  CI result.

## Native evidence and limitations

The approved public files (about 148 MB) were explicitly installed in the new
dedicated model volume and verified. A task-owned ephemeral Docker container
generated an English eSpeak voice from implementation-authored text, then converted
that trusted fixture to 16 kHz mono PCM. Its WAV was 161,806 bytes / 80,881 frames
(about 5.06s). Original test audio was not stored on the host or in application
stores; the generator container was automatically removed. No user project/source,
shared queue/volume, credentials or existing model service was deleted or changed.

Real private inference returned one schema-valid English segment with bounded
timestamps. One diagnostic execution reported **1,176 ms** model-child duration,
including local model setup and transcription. This is a tiny component probe,
not a production/long-input performance benchmark or timestamp-accuracy review.

The final ordinary native protocol probe also passed on the last image, reporting
**1,086 ms**, the same 80,881 input frames and one English segment. Runtime inspection
confirmed non-root/read-only/no-app-credentials/no-published-port/internal-network
and configured CPU/RAM/swap/PID bounds. All nine selected runtime services were
healthy. This ordinary probe intentionally does not assert keyword accuracy.

The initial strict synthetic keyword probe **failed**: the health term was found,
but the expected endpoint term was not. Accepting equivalent `end point` spelling
in the probe did not make that strict check pass either. The model/protocol itself
was available and returned validated text; the vocabulary-quality failure remains
recorded, not reclassified as accurate recognition. The optional keyword probe
still fails on a mismatch. No generated text was published as project evidence.
Default native protocol verification must not be presented as exact transcription
or independently reviewed technical/multilingual quality. English/Turkish
representative speech, silence/noise, technical identifiers, human timestamp labels
and model/difficulty trade-offs require a separate reviewed evaluation.

The existing ignored local AI configuration/credentials are preserved. The extra
ASR service is optional and retains only public weights; its native children exit
after each request. No paid API/cloud inference or automatic request-time model
download was used.

## Required next slice

Implement the dedicated media queue/worker and scoped durable audio/window records,
actor/lease/generation fences, atomic derived-transcript adoption, accepted policy
for original cleanup on all terminal/deletion paths, observable cleanup/retry,
machine-generated provenance/inspection and the authorized bounded upload UI.
Only then enable product WAV uploads. The original-retention policy is accepted
but no product workflow is implied by this stateless service. See ADR 0018 and
`local-asr-plan.md`. Learner-code execution still requires its separate hardened
runner; this media boundary is not a code sandbox certification.
