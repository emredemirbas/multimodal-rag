# Retained OCR indexing and frame citations: validation

Date: 2026-10-27. Scope: ADR 0024 / additive migration 0016. This is private
OCR-text RAG, not public MP4 ingestion, image understanding or Alpha 2 approval.

## Delivered boundary

- Internal scoped command pins a complete gallery, initiating actor and target
  embedding space in a new generation. Separate `tutorial.index_visual` task on
  ingestion; no native provider, raw/object GET/PUT or original eligibility change.
- Literal 1,200-code-point frame slices retain stable frame/offset/content/version
  identity. At most 280 chunks; whitespace-only OCR creates no evidence. Actual
  frame PTS is a point, including zero, not an invented visible-duration interval.
- Hash and approved optional local Qwen embeddings use private eight-document
  batches, float32 vector digests and bounded continuations. Exact scope/actor/
  generation/token/membership/wall-clock checks fence saves and full promotion.
  Complete activation, origin relationships and embedding usage commit together;
  failures preserve previous evidence, unknown tokens remain null and billing zero.
- Full scoped gallery/frame/version FKs, separate gallery/index state, typed
  unreviewed origin on retrieval/answers/history/evidence, protected frame links,
  literal text and honest text-only answer policy. Missing managed origin fails
  closed rather than silently becoming unlabeled tutorial evidence. Saved old
  generations remain inspectable after reindexing; complete deletion covers all
  private chunks/evidence/derived chat and the existing PNG cleanup workflow.

## Software verification

The new suite adds 34 backend cases: literal Unicode/stable offsets/maximum chunk
count and point timelines; hash publication and scoped source filtering; semantic
84-chunk continuation, cancel/retry and accepted token attribution; concurrent
command replay/conflict; wrong-worker exclusion; tenant/project/source/generation/
token/actor/revocation/cancel/delete/lease fences; text/frame/vector/profile/manifest/
missing-row corruption; empty OCR/config drift; actual post-write wall-clock
rollback; scoped FKs; HTTP auth/no-store; and missing-origin search/history/evidence.
Existing legacy upgrades now capture pre-migration evidence directly, then verify
all prior columns/IDs/checksums after two complete migration runs. The current
search adapter is not called against a schema whose required new view is absent.
No old migration file is edited or checksum override used.

Final complete regression: **604 passed, no skips, 150.03 seconds**, including
all existing real worker/MinIO regressions. One upstream Starlette TestClient
deprecation warning remains visible; no test or warning is suppressed.

All broad tests use three newly created disposable PG/pgvector, Redis and MinIO
containers, tmpfs data, allowlisted test-only credentials and `TEST_REAL_WORKER=1`.
No actual `.env`, application schema/bucket/queue/volume is used. Exact new IDs
are cleaned after each run. An initial test-driver bucket-name mismatch made old
parent/worker fixture stores disagree; align only the disposable test environment,
not application settings or assertions. Earlier full runs exposed the transcript
DTO extension and pre-migration test setup; both are corrected, not skipped.

Frontend: **27 files / 143 tests**, lint/typecheck and all **five** actual lint
compatibility checks pass, including CI's **Node 24.21.0** in an ephemeral
network-disabled builder. Production frontend builds pass. Contracts cover point
zero versus transcript intervals, missing/mixed/invalid visual origins and index
state. UI retains exact evidence/frame links, unreviewed OCR, literal hostile text,
gallery/image failure states and no fake player. Full npm audit: **zero findings**;
no dependency, audit threshold or rule is changed.

## Actual worker loss (controlled inference)

A test-owned Celery solo worker uses an isolated Redis namespace/queue/schema.
After eight real DB checkpoint rows commit, pause and SIGKILL only that worker.
Recover its lease, then start a replacement: six remaining chunks finish, with
**14 total fixture embedding calls**, exactly once per distinct input, two
deliveries/two failure attempts and one index usage event. Original/object GET/PUT
is forbidden in both workers. Duplicate completed delivery does nothing; staging
is removed on activation and owned project deletion cleans all fixture artifacts.
This proves queue/checkpoint recovery, not native embedding quality or prefork
signal enforcement. Lost in-flight inference can still repeat.

CI supplies `REDIS_PORT` without requiring `TEST_REDIS_URL`. The new worker test
uses the same optional URL/port fallback as existing probes. Separate repeat with
the explicit URL absent in fresh disposable services: **1 passed, 2.97 seconds**.
No new CI credential, relaxed assertion or application configuration is required.

## Actual native production workflow

A separately tagged production stack runs in a new UUID-named Compose project
with test-only credentials, `--env-file /dev/null`, fresh validated nonexternal
volumes/networks and random loopback ports. No existing app/model data is mounted.
The native service stays credential-free/internal-only, read-only/resource-bounded
with inherited kernel/child socket denial; only its trusted coordinator spans the
application network. The application itself is not restarted or migrated.

The final fresh-stack run **passes**:

1. Generate the existing authored card MP4; privately register authorized input.
   Real scheduler/outbox/visual worker invokes actual FFmpeg/Tesseract once.
2. Publish two retained PNG/OCR frames through actual separate deliveries, PTS
   `[0,10000]`. Existing explicit Turkish `sağlık kontrolü` diagnostic passes.
3. A separate real ingestion job indexes retained OCR in default hash mode at
   generation 3. The production Next BFF/SSE answers `HEALTH CHECK`, citing the
   actual zero-PTS frame and original extraction job, with unreviewed origin.
4. Production evidence SSR shows literal OCR, point timestamp and exact protected
   frame anchor, not a transcript link/player. The actual image proxy returns the
   same verified PNG with no-store headers. Reindex to generation 4; original
   evidence, saved turn replay and history/frame origin remain unchanged.
5. The first probe wrongly compared the browser DTO's deliberately omitted ranking
   score with raw SSE; fix that probe comparison only. Its disposable stack is
   removed, then the complete sequence passes in a new stack, including auth/foreign
   project 401/404, confirmed raw deletion and only two PNG objects remaining.
6. Exactly one native extraction event across publication, both indexes and reads.
   Delete only the owned project through the API, await verified cleanup, assert
   no remaining objects/old evidence, then remove only that disposable stack.

This authored-card/native **hash-index** pipeline is separate from controlled
semantic/recovery fixtures. No new native Qwen/Ollama answer-quality result,
representative scene/code/terminal OCR benchmark or long-video performance is
claimed. `quality_approval=not_established` remains; the earlier combined-language
Turkish exact-term failure and ASR vocabulary limitations are not resolved.

## Delivery limits

Actual `.env` remains ignored/0600, unchanged; existing application services/data
and public weights remain intact. Product MP4 upload, public video reprocess,
scene/vision descriptions and representative quality remain follow-ups. Gallery
publication alone is not indexing; current-space compatibility is separate from
index presence. Hosted CI must match the actual pushed SHA, separately from local
results. No paid/cloud call or automatic model download is introduced.
