# Private visual service validation

Date: 2026-10-26
Scope: stateless private HTTP/native boundary only (ADR 0021).

## Software coverage

The visual unit/loopback suite covers the existing parser plus the new strict
processing identity, wire image/OCR/timeline and HTTP/client boundary. New cases
exercise all three explicit languages, input/profile mismatch, unknown fields,
literal hostile OCR and safe representations/logs; framing/length/encoding/header
rejection before native work; connection/work capacity and failure recovery;
absolute header/body and response-trickle deadlines; rejected proxy/redirect and
malformed/oversized/duplicate/nonfinite/short remote responses; image base64,
SHA-256, CRC, geometry, bounded decompression and exact decoded-pixel duplicates.
Startup ordering and missing-filter failure prevent premature readiness; a fresh
child probe receives no app environment. No provider retry is hidden in the client.

Local complete backend regression uses newly created disposable PostgreSQL,
Redis and MinIO containers, tmpfs data and allowlisted test-only DSNs/credentials,
with `TEST_REAL_WORKER=1`. No actual `.env`, application DB/bucket/queue/volume or
user-owned source is used. Only exact newly returned test container IDs are removed
in cleanup. Final full regression: **459 passed, no skips, 90.46 seconds**, including
actual worker/recovery/storage integration. The combined visual suite contains
135 cases (57 existing parser cases plus 78 private service/contract cases).
Frontend files/dependencies are unchanged in this slice; no new local frontend
result is claimed. Hosted CI retains the frontend audit/lint/typecheck/tests/build.

## Native component evidence

Built the minimal `Dockerfile.vision` image and ran both
`python -m app.vision.http_selftest` and the original `app.vision.selftest` in new
disposable containers: network none, read-only root, 192 MiB tmpfs, 1 GiB memory
and swap ceiling, two CPUs, 32 PIDs, no core dumps/capabilities/new privileges,
no host ports/mounts/app credentials. Both commands exited zero.

The new HTTP probe starts the **actual service entry point** in a fresh child.
Only its prebound container-local listener remains usable after kernel socket/
connect denial; startup verifies a fresh child's inherited restriction before
readiness. The trusted probe parent connects over loopback, sends its authored
20-second MP4, and receives validated PNG bytes plus literal Turkish OCR.

- Four candidates become two unique frames at actual PTS `[0, 10000]` ms.
- The explicit Turkish authored-card diagnostic passes over real HTTP, not a
  fake runner. Both PNG payloads survive strict wire integrity validation.
- A different internally valid pinned identity is rejected before a second native
  extraction. Service logs count exactly one extraction and contain no card text.
- No application record or object is created; no media is exported in the summary.
- FFmpeg `5.1.9-0+deb12u1`, Tesseract `5.3.0`, pinned image Pydantic `2.14.1`.
  Language-data/profile/frame hashes match the earlier
  [native foundation record](local-visual-validation.md).

The original standalone probe also passes unchanged explicit English/Turkish
card checks, inherited socket denial, CLI acknowledgement/stdin and safe malformed
input rejection. Its mixed `en+tr` Turkish exact-term diagnostic is **still false**.
Do not reclassify that failure or these synthetic cards as representative
terminal/code/scene/OCR quality approval. `quality_approval=not_established` remains.

## Compose and delivery boundary

Validated Compose using explicit dummy environment and `--env-file /dev/null`,
never printing the configured application environment. `visual` is opt-in, has no
published ports/mounts/app environment, retains resource/capability limits and joins
only `visual-private` with `internal: true`. No current API/worker/web service joins
that network; normal profile-free startup excludes both visual services.
The existing nine application containers remain healthy and were not restarted.
`.env` remains private (0600) and unchanged. No applied migration was modified.

CI adds separate configuration and actual native HTTP checks alongside the existing
standalone visual check. A local success is not a hosted CI result; the pushed
commit's final GitHub run must be reported separately.

Not delivered: video source registration, durable queue/checkpoints/leases,
tenant/project/actor fences, original expiry/physical cleanup, stored frames,
published visual evidence/retrieval/citations or UI. Those require their own
migrations, recovery/deletion/isolation/UI coverage and task-budget design before
any public video capability is enabled. The provider's 120-second native budget
must not be silently inserted into the current WAV worker's 90/120-second task.
