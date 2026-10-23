# Private media worker and temporary-original validation

Date: 2026-10-22
Status: Private backend component implemented and locally validated. **Product WAV
upload remains disabled** until bounded authenticated upload/BFF/form and explicit
machine-generated provenance/inspection are delivered and checked end-to-end.

## Delivered

- Dedicated optional `media-worker` / media queue and separate application task
  registries; ordinary workers do not register the ASR task. Fixed scheduler routes
  dispatch known job types only. Native inference stays in the existing isolated,
  credential-free service, receiving <=30-second PCM/language only.
- Internal bounded rights-aware WAV registration, scoped concurrent idempotency,
  write-ahead orphan reservation and a separate `audio_inputs` record. No WAV API
  route/form is added. Raw originals are not retained transcript artifacts.
- One window per delivery, immutable ASR checkpoints and successful continuations
  without a failure attempt. Existing late ack/lease/soft/hard/visibility limits
  and bounded retries remain. Lost in-flight inference can repeat; committed
  results are reused rather than recomputed.
- Complete, revalidated VTT adoption under a live fence and a unique reserved
  candidate prefix per attempt. Post-PUT membership/lease/expiry is checked before
  adopting. A failed candidate's cleanup cannot remove a later successful VTT.
- ASR success/usage/provenance, derived-artifact retention, a new ordinary indexing
  job/outbox and raw retirement commit together. No partial index is published.
  Every indexing generation retains the scoped origin ASR-run FK. Reindex uses
  retained VTT; retranscription after retirement requires a new authorized upload.
- Cancellation/permanent failure/revocation/expiry retire raw audio immediately
  for processing. One-hour eligibility includes abandoned queues. Physical deletion
  is confirmed only after object cleanup succeeds; scheduler/storage outages can
  delay it. Retryable and exhausted cleanup remain observable, not called deleted.
- Source/project deletion covers originals, candidate/derived objects and scoped
  metadata/evidence. Content-free logs and aggregate original lifecycle metrics
  accompany accepted frame/model-duration attribution and zero billed local usage.
  Unknown token counts remain null; local hardware/electricity is not free.

## Verification

- Final full backend with PostgreSQL/Redis/MinIO and `TEST_REAL_WORKER=1`:
  **237 passed, no skips** (94.46s).
- Real test-owned media worker is SIGKILLed after its first committed window. A
  replacement resumes window 1; separate media/ingestion queues complete VTT
  adoption and actual indexing. Fixture call counts are exactly one per accepted
  window (0 and 1), with two deliveries/two attempts: one interrupted, one successful.
  Duplicate completed delivery does not create work. MinIO raw-object removal,
  retained VTT, cited answer and complete owned-project cleanup pass.
- This queue/process-loss proof uses **controlled fixture inference**, not native
  speech recognition or word/timestamp accuracy evidence. No new ASR quality claim.
- Covers concurrent registration, idempotency conflict, queue routing, continuation,
  retry exhaustion, unique-candidate rollback/orphan cleanup, source/project delete,
  in-flight cancel/revocation/expiry, idle TTL and cleanup failure/exhaustion/retry.
- Separate post-PUT registration/adoption revocation tests confirm no artifact is
  adopted after access loss. Scoped FKs reject cleanup tickets from another tenant
  or project. Reindex preserves ASR provenance without a new inference call.
- Derived VTT also respects the configured downstream subtitle limit before any
  candidate object is written; an oversized result retires its original safely.
- Current SRT/VTT API regressions still reject WAV. Frontend **17 files / 60 tests**,
  **5 lint compatibility tests**, lint and typecheck pass. UI remains unchanged.
- Compose configuration and API/ingestion/scheduler/migration/media-worker builds
  pass. An ephemeral production media container reaches the existing private ASR
  readiness endpoint and verifies its exact identity/profile without audio input.
  This is connectivity/readiness, not native end-to-end ingestion evidence.
- Final network-disabled/read-only image checks confirm migration 0012 is packaged
  and `pip check` passes. Local `uv --no-cache pip check` and whitespace checks pass.
  `.env` is unchanged
  and remains mode 0600. No original, transcript, secret or raw provider error is
  logged by the new processing code.

## Migration/isolation correction

The first full run passed 234 tests before the final scoped-cleanup FK checks.
The next run exposed `applied migration checksum changed`: the legacy vector test
used the configured application DB, not its isolated fixture, and had applied
0011 there. That test now performs all migration/data/cleanup work inside its
own schema. The checkpoint component's new fixtures were already isolated.

Restore 0011 exactly to its already-applied bytes and put the additional cleanup
ownership/state constraints in new additive migration **0012**. Read-only audit
confirmed application 0010/0011 checksums match the files and **zero application
audio-input rows**. No checksum override, schema reset, rollback or user source
deletion was used. The final full suite passes using isolated schemas. 0012 is
verified in those test schemas, not applied to the running app as part of this slice.

Real process tests use their own schema, Redis namespace/queues/processes and MinIO
prefix; they never flush shared Redis or purge a bucket/volume. Only owned fixture
data/processes are removed. Production images were built, but existing user
services were not restarted. Optional public model weights are unchanged; no
model download or paid/cloud inference was used.

Prior checkpoint commit `a3f7da1` passed
[all hosted jobs](https://github.com/emredemirbas/multimodal-rag/actions/runs/39769170318).
This record is local evidence for the subsequent media backend, not a claim that
its new hosted run has passed.

Follow-up (2026-10-23): private backend commit `f121293` subsequently passed
[all hosted jobs](https://github.com/emredemirbas/multimodal-rag/actions/runs/39774836975).
The next read-only inspection component is recorded separately in
`media-inspection-validation.md`; public WAV upload is still disabled.

## Next product-enablement step

Implement bounded authenticated WAV API/BFF/form, explicit rights/language/temporary
retention/re-upload guidance, processing and cleanup status, and machine-generated
source/evidence inspection labels. Verify a separately reported owned-audio native
end-to-end probe and UI recovery/deletion flows before enabling audio in the app.
Vision/OCR and assignment/grading remain separate later work.
