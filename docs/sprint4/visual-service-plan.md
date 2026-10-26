# Private local visual service boundary

Date: 2026-10-26
Status: Implemented; follow-up to ADR 0021. See `visual-service-validation.md`.

Continue the accepted MP4/OCR scope with a credential-free private HTTP service
and a trusted-worker client. Do not enable uploads, create application records,
install native tools in ordinary workers, or change the user's running stack.
No new retention, model, paid service or product decision is needed for this slice.

- Reuse the stateless parser and inherited kernel socket denial. Bind one private
  listener first; deny new sockets/connect before readiness or native processing.
  Native children receive no listener descriptors or application credentials.
- A separate opt-in `local-visual` Compose service joins only an internal network,
  has no published ports/mounts/app environment and keeps the tool's read-only,
  non-root, tmpfs, memory, CPU, PID and capability restrictions. Do not attach API,
  web or current workers before their authorized durable workflow exists.
- Bound connections, processing concurrency, request reading, native work and
  response size. Reject ambiguous framing, URL/path input, malformed MP4 and
  unsupported languages; do not queue or retry inside the provider.
- Return literal unreviewed OCR and bounded PNG bytes only over this private
  protocol. Validate canonical identity/profile, input hash, sampling/timestamps,
  image hashes/geometry/CRC/bounded decompression and duplicate pixels on both
  sides. Require an explicitly pinned identity for extraction; never silently
  adopt a changed engine/language-data profile on a retry.
- The client accepts only the fixed private service or explicit loopback test
  endpoints, bypasses proxies and never follows redirects. Fail with content-free
  typed errors; log only bounded route/status/count/timing metadata, not media,
  OCR, paths, headers or caller-supplied identifiers.

Test synthetic contracts and real loopback HTTP: framing, capacity/recovery,
deadlines, bad responses, identity/input drift, no fallback, safe errors/logs.
Also exercise the actual credential-free filtered service with authored native
cards in a new disposable container, including a fresh child socket-denial probe.
Add that check to CI without starting application data services for it.

This stateless slice needs no migration or tenant/project records: it deliberately
receives none. Future job orchestration must authorize both scopes, persist the
pinned identity/checkpoints, enforce actor/lease/generation/expiry fences, retire
originals and confirm complete raw/derived cleanup before any product video flag.
No source UI, published visual evidence, scene detector or OCR quality approval is
implied. See Python's [private HTTP server limitations](https://docs.python.org/3.12/library/http.server.html)
and Docker's [network configuration](https://docs.docker.com/reference/compose-file/networks/).

The future queue must budget the provider's full 120-second native work plus
bounded transfer/validation/storage; do not simply reuse the current WAV worker's
90/120-second task deadlines. Select bounded deliveries or dedicated task/lease
limits when that durable slice is designed, leaving existing ASR behavior intact.
