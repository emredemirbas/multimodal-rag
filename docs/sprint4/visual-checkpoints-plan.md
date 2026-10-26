# Private durable visual result checkpoints

Date: 2026-10-26
Status: Implemented; next bounded component of ADR 0021. Validation is recorded in
`visual-checkpoints-validation.md`.

Persist the accepted private provider result before future object adoption, without
opening video uploads or connecting native decoding to current workers. No paid
provider, broader format/retention or new product decision is introduced.

- Add migration 0013 only; preserve every applied migration. A scoped visual run
  pins the actual MP4 digest/byte count, initiating actor, rights assertion and
  complete engine/language-data identity before inference.
- Save a complete validated result atomically: <=20 PNGs, <=12 MB image bytes and
  <=320,000 OCR characters. Bounded PNG bytes temporarily live in private PostgreSQL
  staging, not public evidence or final object storage. This avoids introducing
  untracked object PUTs before the later adoption/cleanup workflow exists.
  These permitted derived bytes remain until source/project deletion or later
  adoption cleanup; the processing deadline is not a physical deletion deadline.
- Preserve actual PTS, sampling/video metadata and image/OCR/result hashes. Recheck
  the existing strict wire format on writes and reads. A duplicate delivery never
  overwrites an accepted snapshot or counts it twice; corruption fails closed.
- Begin/save/load require the initiating membership, both tenant/project scopes,
  exact source/job/generation/token, live lease and unchanged video/visual input.
  Lock membership through the transaction and recheck wall-clock eligibility
  before returning/committing. Processing expires one hour after **job creation**,
  never one hour after a retry or first checkpoint. That is an eligibility limit,
  not a claim of physical raw-media deletion.
- A lost lease may resume the saved complete result without another native call.
  An interrupted in-flight extraction can repeat the whole bounded call: this is
  **not per-frame decoder resumability** or exactly-once inference. Current native
  HTTP extraction returns a complete batch; do not imply finer progress.
- Keep staging out of retrieval, transcript/evidence APIs and usage_events. Record
  accepted frame/image/OCR counts in aggregate content-free operational metrics
  and scoped metadata logs, not fabricated tokens/model duration/billing.
- Source/project deletion must cascade through all checkpoint bytes/text. This
  component makes no object-store call, registers no source/job, publishes no
  queue message and does not complete/activate a job/source.

Test real isolated PostgreSQL: concurrency, duplicate/no-overwrite, retry/lease
recovery, input/profile/rights/actor drift, expiry, atomic rollback, corruption,
scope/ownership FKs, source/project cascades and migration preservation. Existing
subtitle/chat/WAV and private native-service regressions must remain green.

The next slice still needs video registration, original object reservation/expiry/
confirmed cleanup, dedicated queue execution/task budgets and atomic derived-frame
adoption before any product video UI or visual retrieval/citations are enabled.
Do not fit a 120-second provider call into the current WAV worker's 90/120-second
delivery limits. No existing application migration/service/data is changed by tests.

Primary concurrency references: PostgreSQL 16 [row-level locks](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS)
and [wall-clock versus transaction time](https://www.postgresql.org/docs/16/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).
