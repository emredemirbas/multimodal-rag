# Private ASR checkpoint validation

Date: 2026-10-21
Status: Component implemented and locally validated. **Not a product audio-upload
workflow**, an ASR quality benchmark or full Sprint 4 completion.

## Delivered boundary

- Migration 0010 adds private, composite-scoped ASR runs/windows tied to an
  existing job/source/generation, with at most twenty 30-second windows.
- Original WAV hash/frame count, requested language, approved provider/model/
  revision/engine/network profile and assembly version are pinned. Resume refuses
  changed input/profile/language. No original audio is stored by this component.
- Every begin/save/assembly uses the existing live project, actor membership,
  generation, job-token and unexpired-lease fences. ASR job type is checked;
  ordinary ingestion claims leave ASR jobs untouched without consuming attempts.
- Ordered, revalidated, size-bounded results advance one cursor atomically.
  Concurrent/duplicate writes cannot overwrite text or count accepted frames/model
  duration twice. Checksums are canonical across JSONB's signed-zero normalization.
- Complete-run assembly preserves absolute timestamps and silent windows, marks
  output machine-generated, escapes/normalizes text and checks existing subtitle
  limits. Entirely silent input fails without inventing evidence. Incomplete,
  missing, corrupted or incompatible results cannot become a derived artifact.
- Returned bytes/digest/profile are immutable; no source activation, object PUT,
  model request, new job completion or published usage event occurs. Private text
  never enters retrieval, transcript browsing or citation inspection.
- Source/project deletion cascades staging. Cancel/revocation/stale claims cannot
  use or recreate it. Content-free checkpoint logs and aggregate saved-window,
  frame and model-duration gauges supplement existing processing metrics.

## Verification

- Final full backend with PostgreSQL/Redis/MinIO and `TEST_REAL_WORKER=1`:
  **217 passed, no skips** (78.51s). This includes existing real-process worker
  death, checkpoint recovery, playlist and object-deletion regressions.
- **31 new checks**: 9 pure VTT/validation cases and 22 private PostgreSQL cases,
  including parametrized fences/corruption. Fresh/Sprint-0 upgrades and repeatable
  migrations pass; existing hash evidence/citations remain intact.
- Actual concurrent PostgreSQL saves accept exactly one result. A test-owned
  expired lease is recovered and re-claimed; the next cursor starts after the
  committed window, with no partial publication or duplicated accepted duration.
- Negative tenant/project/source/generation/token/membership/cancel/source-delete/
  project-delete operations fail closed. Corrupt payload/hash/length/profile/usage
  and scoped FK mismatch fail. All-silent and maximum-duration assembly are covered.
- API regression confirms both WAV MIME and generic-binary WAV uploads remain
  rejected, with no ASR run created. Current subtitle behavior is unchanged.
- Frontend regression: **17 files / 60 tests**, **5 lint compatibility tests**,
  lint and typecheck pass. No form/UI contract changed.
- API/ingestion-worker/scheduler/migration Docker builds pass. An ephemeral
  network-disabled/read-only production container imports the modules and verifies
  migration packaging. Image `pip check` and local `uv --no-cache pip check` pass.
- `git diff --check` passes. Ignored `.env` remains unchanged with mode 0600.

No user project, shared queue, existing service or volume was deleted/restarted.
PostgreSQL fixtures create/drop only their isolated schemas and owned namespaces;
WAV fixtures exist in test memory only. The temporary packaging containers use
`--rm`, no credentials, no mounts and no network. No model download, paid API or
native ASR request was needed. The current migration was verified in isolated
test databases, not applied to the user's running application database.

The new ASR lease-expiry test is **not** an actual media-worker SIGKILL test or
proof of end-to-end audio processing. Existing real-worker tests protect the
unchanged subtitle/indexing pipeline. Native recognition limits in
`local-asr-validation.md` remain unchanged. No new word/timestamp accuracy is claimed.
The hosted result for this component has not yet been verified; the successful
hosted run for `fb37596` does not cover these checkpoint changes.

## Required next step

Implement the dedicated media worker/queue and scoped temporary-original lifecycle,
observable cleanup on terminal/deletion/revocation paths, and atomic derived-VTT
object adoption into transcript indexing. Verify real media process-loss/retry and
cleanup races before enabling an authorized bounded upload/BFF/form with explicit
machine-generated provenance and inspection/correction guidance.
