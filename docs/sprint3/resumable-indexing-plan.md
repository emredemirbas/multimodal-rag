# Resumable local semantic indexing

Date: 2026-10-12
Status: Implemented and locally validated; see `resumable-indexing-validation.md`.
Authorized continuation of the earlier ingestion/RAG slice.

Replace the 128-chunk semantic-only rejection with durable checkpointed work under
the already accepted 2 MB / 20,000-cue / 10,000-chunk input limits. No new media,
provider, network destination, model download, paid service or quality claim.

Material assumptions and delivery:

- Add migration 0008. Pin the target embedding space at job creation; legacy jobs
  pin it on their first new claim. Changing mode mid-job fails with a safe recovery
  instruction rather than mixing spaces. Reprocess creates a new target/generation.
- Private scoped staging rows hold validated batches, never searchable evidence.
  Persist an ordered chunk-ID manifest hash to reject changed parser/input output.
  Every checkpoint/finalization uses the existing project/actor/lease/generation
  fence. A lost worker resumes at the last committed cursor, not the last response.
- Eight documents/batch, at most eight batches (64 segments) per delivery. Stop
  starting inference after 48 seconds; existing 20-second inference/manifest and
  90/120-second task limits remain. Defer unfinished work through the outbox with
  a two-second delay, releasing its playlist slot. Continuations do not consume
  bounded failure retry attempts; delivery count remains independently observable.
- Promote all staged segments and activate the generation in one transaction.
  Preserve old evidence/citations until success. Aggregate accepted batch tokens
  and actual delivery durations; unknown tokens stay null, billed API cost zero.
- Cancellation preserves checkpoints for explicit retry; reprocess discards only
  unfinished staging for the superseded generation. Source/project deletion also
  cascades staging. Queued stale ID-only tasks cannot recreate it.
- Show completed/total segment counts and automatic continuation status through
  existing authenticated polling. Keep failed retry and automatic continuation
  distinct, with safe model/parser-change guidance and loading/success states.

Verify scoped/foreign/stale writes, duplicate delivery, parser/model drift,
pause/retry/cancel/deletion, upgrade preservation, real SIGKILL after a checkpoint
in an isolated worker namespace, 129+ chunks across multiple deliveries, complete
offline suites and a separate native-model/worker smoke. Do not touch user data or
shared queues/processes. No commit/push without a new owner request.
