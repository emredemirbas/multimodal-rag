# Experimental MP4 upload verification

Date: 2026-10-27. Scope: ADR 0026, no new schema or applied-migration edits.
Default `VIDEO_UPLOAD_ENABLED=false` remains unchanged. Hosted CI is checked
separately after push; these are the local verification results.

## Software and protocol evidence

- Final full backend run: **670 passed, zero skipped, 162.39 seconds**, including
  actual owned worker SIGKILL/recovery with `TEST_REAL_WORKER=1`. Fresh test-only
  PostgreSQL/pgvector, Redis and MinIO used random loopback ports and memory-backed
  disposable data. Only recorded new container IDs were removed. One existing
  upstream Starlette/httpx TestClient warning remains unsuppressed.
- API tests cover strict independent default-off flag/fixed configured capability,
  authentication/gating before body reads, actual streamed bytes with false
  Content-Length, file-byte vs wire limits, timeout/disconnect, per-process busy
  admission/slot release, missing/extra/duplicate multipart fields, rights, explicit
  OCR language, ack, MIME/container/name, tenant/project/archive and unchanged
  subtitle/chat/WAV limits. Acceptance enqueues the existing automatic pipeline;
  API inference is absent. Original receipt/key replay survives generation 3.
- Source inventory covers temporary/expired/retired/pending/failed/deleted raw
  lifecycle independently of current source generation. A failed unrelated orphan
  is not proof that this raw-original ticket failed. Verify scoped original cleanup
  failure/retry, foreign tenant/project rejection, independently confirmed deletion,
  no original resurrection and complete source/project cleanup. No key or private
  input digest is projected.
- Final frontend production builder uses **Node 24.21.0**. Network-disabled
  verification: **30 files / 169 tests**, five real lint compatibility tests,
  ESLint with zero warnings, TypeScript checks and production build pass.
  The unchanged dependency graph's full npm audit reported zero vulnerabilities.
- BFF tests cover Origin/UUID/capability before reads, actual 100 MB wire overflow,
  timeout/reader cancellation, excessive multipart markers split across chunks,
  duplicate/unknown fields including forbidden playlist/URL input, byte/type/rights/
  language/consent checks, admission and release, scoped original-job receipts,
  changed rights/language/filename, malformed/mixed retention and completed replays.
  A malformed receipt stays an uncertain delivery, not an invented success or
  rollback; only safe IDs reach the browser and the same request key is retained.
- UI tests cover labelled required consent, honest scope/quality caveats, empty/
  invalid/pending/success/error states, single submit, stopped delivery vs job
  cancellation, uncertain unchanged draft/key retry, foreign receipt rejection,
  accepted-but-refresh-failed, default-off/unavailable/archived form gating,
  cleanup polling after completed jobs and stopping on confirmed deletion. Cleanup
  retry submits only the scoped ticket and never invents physical deletion.

## Actual native / production boundary evidence

Built separate API, ingestion-worker, visual-worker, production frontend and test
builder image tags. Reused the unchanged isolated minimal native image. A fresh
UUID-named Compose project used test-only credentials, `--env-file /dev/null`,
random host ports and validated new non-external volumes, never application data
or model volumes. Preflight verified private native network/no app credentials/
ports/mounts. Only this disposable API was explicitly opted in.

The committed authored smoke's public mode submitted an owned two-card MP4 through
the actual production Next BFF and authenticated FastAPI multipart boundary.
Configuration/form/retention SSR, sanitized receipt and unchanged request-key
replay passed. Real FFmpeg/Tesseract plus visual/ingestion workers automatically
reached generation 3, retaining two frames at PTS **0 / 10,000 ms**, explicit Turkish
OCR and original processing identity. A question returned a frame-backed zero-PTS
citation; protected production evidence SSR/PNG and source-gallery links passed.
All three jobs retained the original actor and exactly two zero-billed usage
events were accepted. Raw-object deletion was independently confirmed while the
permitted two PNGs remained, and the source SSR displayed the confirmed lifecycle.

The same production path also accepted an actual **100,000,000-byte MP4** and a
scoped cancellation. This is the authored MP4 padded with a valid ISO `free` box,
not a larger/longer media allowance or representative high-bitrate decode test.
The persisted byte count was exactly 100,000,000. API's previous 64 MiB tmpfs
would not fit its multipart spool; the bounded 256 MiB change was verified through
this real request, without raising subtitle, WAV, chat or Server Action limits.
Complete API project deletion then removed all input/checkpoint/workflow/index/
evidence references and objects, with independently tracked cleanup completion.

CI's image job now explicitly opts in only its disposable stack and runs this
public native/retention/100 MB smoke. Normal startup remains default-off.
Local teardown removed only the validated fresh Compose project's volumes and
networks. The user's `.env` remains ignored/mode 0600, current application data and
running services were not changed, and no user database migrations were applied.

## Limits / non-claims

No new dependency, automatic model/weight download at inference, paid/cloud model
call, video player, audio
transcription, URL download, playlist association, scene detector, vision
description or public video reprocess. Capability is configured availability, not
readiness/accuracy. All original eligibility/cleanup and permitted-derivative
retention rules remain unchanged. One active delivery is per process, not a
deployment-wide quota or a multi-user load benchmark. Authored cards and padded
upload bytes do not establish representative code-OCR, combined-language quality,
scene recall, full 10-minute/high-bitrate processing performance or Alpha 2 quality.
