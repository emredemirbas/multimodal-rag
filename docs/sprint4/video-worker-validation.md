# Private MP4 job lifecycle validation

Date: 2026-10-26. Scope: ADR 0022 / additive migration 0014, private prepared-only
coordination. This is not public MP4 ingestion, visual retrieval or Alpha 2 completion.

## Local regression

**535 passed, no skips, 113.64 seconds**: `python -m pytest backend --tb=short`
with `TEST_REAL_WORKER=1`, fresh PostgreSQL/pgvector, Redis and MinIO containers,
allowlisted test-only credentials and tmpfs data. No actual `.env`, application
DB/bucket/queue or volume was used. Only exact newly returned container IDs were
removed afterwards. Existing services were not restarted or migrated.

The new files add 34 cases (33 DB/coordinator cases and one actual worker test):

- Concurrent idempotent registration accepts one source/job/input/object/outbox;
  changed requests conflict. Invalid MP4/name/request key/rights/language and
  foreign tenant/project/actor or archived project cannot adopt input.
- A committed unique-prefix reservation cleans orphan PUTs after interruption or
  real membership revocation. Original processing expiry equals job creation +
  one hour and cannot be extended by retries.
- Actual accepted frame/input counts and processing-attempt duration are recorded
  once, with zero local billed usage, unknown token count and no embedding space.
  Successful jobs are `visual_prepared`; sources stay `metadata_ready` with zero
  published segments/frames, no active generation, and abstaining retrieval.
- A transient service failure keeps the original for bounded retry; exhaustion
  and permanent profile changes retire it. An incomplete pinned identity cannot
  auto-update. Generated object keys and raw byte/digest bounds are checked before
  provider construction. Cached preparation revalidates input records too.
- Cancellation, idle expiry, revoked membership and in-flight cancel/revoke/source
  or project deletion prevent snapshot publication/preparation and retire raw data.
  Complete deletion removes every private checkpoint/input row and object.
- An actual SQL delay expires the wall-clock lease after completion/usage/cleanup
  writes: the transaction rolls all of them back. Cross-project cleanup FKs fail;
  cleanup failure/exhaustion is visible to its scoped initiator and is never
  falsely reported as physical deletion. Existing generic cleanup retry controls
  remain unchanged.
- Migration runner upgrades pre-0013 published transcript data through 0013/0014
  twice, preserving prior migration checksums and stable citation IDs. No prior
  migration is edited. Existing 42 checkpoint integrity/isolation tests still pass.

## Actual queue/process-loss evidence

The test starts a test-owned Celery visual process with an isolated Redis key
prefix/queue and a real MinIO original. Inference is an explicitly synthetic
fixture, **not native OCR**. SIGKILL occurs after the real complete checkpoint has
committed; only that owned process is killed. After lease recovery and outbox
dispatch, a replacement finishes with provider construction and raw GET forbidden.
There is one fixture extraction and one usage event across two deliveries/attempts.
A duplicate completed message makes no additional attempt. The MinIO object's
content type is `video/mp4`; cleanup verifies actual object absence, while the
prepared checkpoint remains private until full project deletion.

This is not exactly-once inference: a lost in-flight extraction may repeat the
whole native call. The process-loss test uses Celery's solo pool; it proves actual
delivery/checkpoint recovery, not prefork signal enforcement. Production visual
worker uses the ordinary prefork pool with separately tested 180/210-second soft/
hard limits, 240-second DB lease and configured 300-second visibility. Other worker
limits remain 90/120 and 240-second visibility; the shared broker's shorter value
still exceeds visual hard execution.

## Image/network/native component evidence

- Built the new backend `visual-worker` target. An actual network-none/read-only
  image run checks task registration, 180/210/300 budgets and absence of FFmpeg/
  Tesseract executables. All three workers' task registries are independent.
- Dummy-only Compose rendering verifies only `visual` and `visual-worker` join
  the internal visual network; only the trusted coordinator also joins the app
  network. No mounts/host ports are added. Native service receives no app
  credentials. Normal startup excludes all optional visual services.
- Re-ran the actual private native HTTP self-test in the existing minimal image,
  in a fresh network-none/read-only/resource-bounded container without mounts or
  credentials. Authored MP4 returns four candidates, two PNG/OCR frames, PTS
  `[0,10000]`, expected explicit Turkish OCR, profile drift rejection and inherited
  kernel/child network denial. Application records created: zero.

The native HTTP component test and synthetic durable-worker test are **separate**,
not a claim of one combined native end-to-end test or representative OCR quality.
`quality_approval=not_established` remains. Mixed-language/scene quality is not
approved. CI now builds/checks the optional trusted worker alongside the existing
native component probes; hosted results must match the actual pushed SHA.

## Remaining gates

No frontend/dependency files, public API/BFF capability or normal default startup
changed. Required next work: final derived-object adoption with stable published
provenance, visual indexing/evidence/citations, accessible authorized upload/status
UI, combined native workflow probe and representative scene/code/OCR evaluation.
