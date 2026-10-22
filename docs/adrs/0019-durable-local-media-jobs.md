# ADR 0019: Durable private local WAV jobs and original retirement

- Status: Accepted implementation of ADR 0018's authorized backend follow-up
- Date: 2026-10-22

Use a dedicated optional media worker/queue, not the API or ordinary ingestion
worker, for ASR coordination. Only the private model service performs native
inference; it still receives PCM/language, never application credentials or IDs.
Application task registries are separate and scheduler routes only known types.

Private WAV registration enforces the existing rights, 20 MB/10 minute/PCM limits,
idempotency and project scope. Commit an orphan cleanup reservation before a
bounded object PUT, then adopt the temporary original/job/outbox atomically.
Public WAV registration/BFF/form remains disabled pending the user-facing slice.

One window per delivery fits existing 90/120-second task limits and 180-second
leases. Accepted windows are durable; continuations do not consume failure retries.
Bounded failures preserve the input until success or terminal retirement. A lost
in-flight call may repeat; do not promise exactly-once inference.

Safety assumption surfaced to the owner: original processing eligibility expires
after one hour, including abandoned queues. This is not a guarantee of physical
deletion while the scheduler/object store is unavailable. The scheduler retires
expired, revoked or terminal inputs and persists observable bounded cleanup. Mark
physical deletion only after verified storage cleanup; failed cleanup stays
failed/retryable. No whole queue, bucket or user volume is purged.

Adoption recomputes the complete validated VTT under the live project/job fence.
Each candidate has a unique reserved prefix, so a stale attempt's cleanup cannot
delete a replacement's adopted VTT. Recheck membership/lease/expiry after PUT.
Atomically retain the artifact, finish ASR, record actual frames/model duration
and zero billed local usage, enqueue ordinary transcript indexing, and retire raw
audio. Unknown token counts remain null. No partial index becomes evidence.

Derived artifacts and every indexing generation retain a scoped ASR-run FK.
Reindexing uses the retained VTT; retired originals cannot be resurrected by retry
or reprocess. Retranscription requires a new authorized upload. Source/project
deletion covers raw/candidate/derived objects and all scoped relational provenance.

Migrations 0011/0012 are additive. Preserve an already applied file/checksum:
new ownership constraints belong in a new migration. All integration probes must
use isolated schemas; the legacy public-schema vector probe is corrected in this
slice. Native word/timestamp quality is separate from queue/recovery evidence.
