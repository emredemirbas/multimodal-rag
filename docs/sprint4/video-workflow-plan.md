# Durable selected-frame/OCR workflow

Date: 2026-10-27. Status: Implemented; local verification complete. ADR 0025.
See `video-workflow-validation.md`; hosted CI is checked after push.

This is an internal prerequisite for the later default-disabled MP4 upload form,
not public video enablement or full Alpha 2. Keep the accepted format, language,
raw one-hour eligibility, permitted derivatives, isolated native service and free
local providers unchanged. No user `.env`, application data or running services
are migrated/restarted as part of verification.

Material assumptions for this small slice:

- Private registration explicitly opts into `auto_process=True`; existing manual
  registrations keep their old behavior and replay hash. Mode changes conflict
  with the original request key. Replays return the original receipt, not another
  upload or a configuration-dependent replacement.
- Pin the configured embedding space when accepting the input. The visual worker
  must not choose its own default at handoff. A later incompatible embedding
  worker fails honestly rather than relabeling evidence or downloading a model.
- Finish extraction and create gallery job/outbox in one PostgreSQL transaction;
  finish gallery and create index job/outbox in another. Retain both child job
  identities in a scoped workflow record. A rolled-back or expired parent cannot
  leave a child, retire raw input or publish partial evidence.
- An already accepted workflow continues through project archival, as ongoing
  work does; archive is not cancellation. New uploads/manual commands still
  require an active project. Cancellation targets the current child and no later
  stage starts until its original initiator explicitly retries it. Revocation
  prevents all writes. Extraction terminal paths require a fresh upload; derived
  retry uses retained results without native inference or raw resurrection.
- Preserve the original actor through every automatic transition. Reject derived
  retry by a different member before mutating the job. Authorized same-tenant
  inspection remains unchanged.
- Add only migration 0017, scoped foreign keys, bounded metadata-only handoff logs,
  and no additional fabricated usage. Complete deletion cascades the workflow.
  Existing status UI already follows the latest source generation; no new public
  UI contract is introduced here. Upload/retention UI is a separate next slice.

Verify happy path, stable old citations, replay/concurrent delivery, rollback at
both handoffs, final wall-clock expiry, cancellation/retry, revocation, archived
continuation, target-mode drift, full scope/FKs and deletion using fresh disposable
services. Separately run the actual native parser + production queue workflow;
fixture OCR is not native quality evidence. Push only after local verification,
then inspect all four hosted CI jobs.
