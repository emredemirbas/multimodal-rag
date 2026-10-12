# ADR 0017: Fenced, resumable semantic batches

- Status: Accepted for the owner-authorized ingestion/RAG follow-up
- Date: 2026-10-12

Replace ADR 0016's initial 128-chunk rejection with bounded deliveries under the
existing authorized transcript caps: 2 MB, 20,000 cues, 10,000 chunks. No new media,
provider, download, paid API or retention class. Hash mode remains the lightweight
default; semantic checkpoints apply only to the approved immutable Qwen space.

Pin target space on new jobs; legacy uninitialized jobs pin it on the first claim.
Validate provider/model/manifest/dimension identity and an ordered stable segment-ID
manifest on every resumed parse. A changed configuration/input fails safely;
restore the original mode/parser to retry or explicitly reprocess into a new
generation. A weight-tag change still fails the native adapter's manifest checks.

Store each validated eight-document batch in private `embedding_checkpoints` with
tenant/project/job/source/generation/ordinal identity and a scoped target-space FK.
Every write checks project, actor membership, current source generation and live
claim token/lease. Staging is never retrieval evidence, never cited or inspectable
through the evidence API. A duplicate/stale batch cannot overwrite a checkpoint.
Only committed progress is reusable; in-flight inference can be repeated after loss.

At most eight batches (64 new segments) per delivery; do not start inference after
48 seconds. Existing inference/manifest bounds and 90/120-second task limits remain.
Defer unfinished progress atomically with outbox redelivery after two seconds,
clear the claim and release the playlist slot. No-progress deferral becomes a
bounded retryable failure, preventing endless empty continuations.

Continuations retain the logical failure attempt. `delivery_count` independently
records executions; historical `processing_attempts.attempt_number` is its sequence.
Completed unfinished executions close as `checkpointed`. Worker loss/provider
failure still consumes existing bounded retry attempts, with a fresh lease and
saved cursor. Manual retry/cancel semantics and maximum attempts remain unchanged.

Verify completeness and ordered manifest, then promote all staged rows, persist
processing metadata/usage, switch the active generation, mark success and delete
staging in one transaction. Do not buffer a whole 1024-D index in Python memory.
Previous evidence and citations remain unchanged on incomplete/failed replacement.
Usage stores accepted batch tokens (unknown stays null), cumulative delivery/attempt
durations excluding queue waits and zero billed API cost. Interrupted calls with no
accepted checkpoint do not contribute fabricated usage. Hardware work is not free.

Cancel retains private checkpoints for explicit retry. Reprocess discards only
superseded unfinished staging, creating a fresh generation. Source/project deletion
cascades it alongside evidence/versions/chat; durable object cleanup and harmless
stale ID-only queue messages remain unchanged. No shared queue/volume purge.

Expose saved/total/delivery counts through existing scoped polling, with distinct
automatic-continuation and failed-retry states. Log counts/versions, never input or
vectors; operational metrics use bounded aggregate labels. Tests include actual
SIGKILL after a committed batch using an isolated fixture provider, and separately
reported native-model indexing. This is reliability evidence, not quality approval.
