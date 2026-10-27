# Change-candidate prototype verification

Date: 2026-10-27. Scope: isolated operator-only sampling experiment. It does not
change application sampling, managed visual identities, checkpoints or citations.
No representative scene/code-quality or full Sprint 4/Alpha 2 approval.

## Software evidence

- **39 new tests** pass (0.10s): actual-PTS anchors/earlier ties, static views,
  pixel/noise thresholds and count arithmetic, changed-fraction/magnitude ranking,
  maximum 600-sample/20-point budget, omitted changes, transient views and returns,
  tiny durations, fractional source FPS, missing/gapped/unordered/duplicate PTS,
  geometry/type/byte limits and immutable private pixels.
- Native-coordinator tests use fixed fake FFprobe/FFmpeg output, not actual scene
  quality. They check demuxer/protocol/external-reference restrictions, source PTS
  handling, output sentinel/count/byte/filename/symlink/geometry/deadline rejection,
  temporary cleanup and missing isolation/invalid input before native construction.
  Standalone identities are explicitly rejected by managed `VisualIdentity`.
- Combined visual regression: **224 passed, 1.92s**. The initial sandboxed run
  could not create loopback sockets (`EPERM`); the identical tests then passed
  with normal local socket permissions and an allowlisted test-only environment.
  No assertion, isolation filter, timeout or test was removed/suppressed.
- Full backend: **758 passed, zero skipped, 171.65s**, with `TEST_REAL_WORKER=1`,
  new disposable PG/pgvector, Redis and MinIO containers, random loopback ports,
  test-only credentials and tmpfs data. No application `.env`, data volumes,
  database/bucket/queue were used. Teardown removed only newly recorded container
  IDs. Existing real process-loss/checkpoint/authorization/deletion tests pass.
  One upstream Starlette/httpx TestClient warning remains unsuppressed.

Applied migrations and all managed profile/wire/checkpoint-digest code are
unchanged. This component creates no project-owned record and adds no HTTP route
or model dependency; application authorization/retry/deletion remains exercised
by the full regression, not implemented by a stateless prototype.

## Actual isolated native comparison

Built a separately tagged minimal native image and used a new disposable
network-none/read-only/non-root container with 192 MiB tmpfs, 1 GiB RAM/no extra
swap, two CPUs, 32 PIDs, no capabilities/core dumps/new privileges, no host/app
data mounts or credentials. The inherited kernel socket restriction is installed
before the existing resource-bounded native wrapper decodes anything.

The authored 20-second 960x540/2fps H.264 clip has a fixed brief view at
`[3000,4000)` ms, then returns to the original image. Input SHA-256:
`54e26514f56e7e9b609423be159eb35105a58a15c308ff741957855b863d89eb`.
FFmpeg is `5.1.9-0+deb12u1`; standalone policy/profile are separately versioned.

- The **actual existing** uniform extraction/OCR pipeline has four candidates
  and retains only PTS `[0]` after exact-image deduplication; it misses the brief
  authored view. This is not a simulated/theoretical baseline.
- The new scan observes 20 actual thumbnails, finds two eligible changes and
  proposes six points: **`[0,3000,4000,7000,13000,19000]`**. Both the brief view
  and temporal return are retained. Changed-pixel fraction is 997,569 ppm and
  mean absolute difference 982,224 ppm at both transitions; no score is labeled
  a probability, semantic confidence or approved quality threshold.
- The actual standalone stdin CLI produces the same content-free proposal and
  malformed input exits 1 without echoing its bytes/raw exception. The existing
  private HTTP/native/profile-pinning smoke also passes in the expanded image,
  including the separate authored Turkish OCR/PNG transport and kernel/child
  restriction. Application records created: **zero**.

These are tiny authored high-contrast transitions, not representative terminal,
code-edit, slide, sub-second, animation, OCR or semantic retrieval benchmarks.
The 600-sample bound is unit-tested; no new native 10-minute/high-bitrate
performance result is claimed. Existing native CPU/wall limits may reject complex
inputs. Earlier mixed-language OCR and ASR vocabulary limitations remain unchanged.

## Delivery boundary

The native image now packages the two operator modules; CI adds the actual
authored comparison alongside the unchanged native/HTTP and application checks.
Hosted results must match the pushed SHA and are separate from these local tests.
Frontend source/dependencies, upload defaults, `.env`, user data and running app
services are unchanged. No application migration or service restart was performed.
No cloud/paid call or model download was needed.

Managed integration remains open: versioned candidate-manifest persistence and
protocol/policy, legacy checksum/history compatibility, job/auth/retry/deletion
coverage and truthful UI. Do not present this operator experiment as active
scene-aware retrieval or as completion of Sprint 4.
