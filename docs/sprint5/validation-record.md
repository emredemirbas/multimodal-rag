# Sprint 5 — validation record

Date: 2026-10-29. Status: internal contracts, saved contexts, versioned draft APIs
and durable queued delivery/atomic draft publication implemented. Model
extraction/generation, review/activation UI and full Sprint 5 acceptance remain undelivered.
The ordered plan is `implementation-plan.md`.

## Starting state and documentation

The initial worktree was clean at `340fd44`; local and remote main matched.
That exact commit's four hosted jobs were subsequently verified
**completed/success** in
[run 40857913140](https://github.com/emredemirbas/multimodal-rag/actions/runs/40857913140).
It does not certify the new Sprint 5 code before that code's own hosted run.

The owner explicitly requested Sprint 5 planning followed by implementation and
professional README content. README now explains product capabilities, quickstart,
usage, architecture, constraints and development links. Sprint/completion/CI
history and test-count trivia were removed. Detailed operator instructions moved
to `../local-development.md`; the continuing README rule is in `../../AGENTS.md`.
README cleanup is separately committed as `5b793b3`.

The brief, requirements, sprint plan, data outline, testing strategy, decisions and
current delivery status reflect the newly authorized scope. The accepted earlier
RAG milestone and unresolved independent real-video/Alpha 2 review remain intact.
Extension policy and official-document fetch/approval policy were requested from
the owner; neither is silently confirmed while an answer is pending.

## First slice — internal boundary

- `backend/app/curriculum/contracts.py`: scoped source/version pins, explicit
  learner preferences and permissions, objectives, labelled requirements,
  acceptance criteria, qualitative rubric, ordered hint content and strict drafts.
  No difficulty/duration/source/permission default is silently selected.
- `validation.parse_draft`: bounded raw model JSON with strict types, unknown-field
  rejection and duplicate-key rejection at every depth; fixed safe errors omit
  input/source/model text. The raw JSON entrypoint accepts UUID text as JSON, not
  arbitrary Python-type coercion.
- `validation.bind_assignment`: resolve model-supplied segment/excerpt IDs from
  trusted same-tenant/project, selected-source snapshots. Preserve the existing
  `EvidenceView`, ASR/visual origins, exact time, processing version and retained
  generation. No model-provided filename, timestamp or fabricated retrieval score.
  Rebuild mutated/constructed model instances and detach accepted projections.
- Reject duplicate source/evidence/document/excerpt/local identities, missing or
  foreign IDs, source/version drift, dangling references, uncovered requirements
  and incomplete requirement -> acceptance -> rubric links. Respect explicit
  prerequisite/extension/document permissions and learner effort.
- Distinguish tutorial evidence from already-authorized official-document snapshot
  metadata. Document binding requires an explicit exact HTTPS hostname allowlist,
  scoped snapshot, retrieval timezone, explicit known/unknown version and matching
  excerpt hash. No domain is approved by default and no URL is fetched.

Technical bounds are explicit resource limits, not quality thresholds: draft JSON
<=256,000 UTF-8 bytes, <=20 selected sources/objectives, <=50 requirements and
acceptance criteria, <=20 rubric entries, <=10 ordered hints and <=10 evidence IDs
per item. Authoritative tutorial context is a subset, <=500 segments/500,000
characters across all snapshots; exceeding it fails early without reading later
snapshots or silently claiming full-source coverage. <=20 document snapshots have
<=20 excerpts each. Explicit effort is 1..10,080 minutes with no duration default.
These snapshot limits are not the future local-model prompt budget.

## Actual checks

- Initial 71 component cases passed. Independent review exposed missing parser/
  visual-origin binding: six new negative cases failed before the correction.
  OCR-only origins now require `visual-ocr-chunks-v1:gN`; mixed descriptions require
  `visual-evidence-chunks-v2:gN` with existing extraction/description/index order.
  Frame evidence cannot claim an ASR transcript origin. A positive mixed-origin
  case preserves the exact existing description identity.
- Final focused component suite: **78 passed**. Cases cover scope/source/generation/
  parser drift, retained old versions, missing and duplicate IDs, detached existing
  provenance, raw JSON ambiguity/size/unknown fields/coercion, constructed/mutated
  model bypass, graph references, explicit permissions and hostile URL metadata.
  All data is synthetic and no network/model/DB service is used by these tests.
- The first validator used an `extra=` call keyword absent from the declared
  Pydantic 2.10 API. It now relies on the domain models' `extra='forbid'`
  configuration and preserves the existing dependency range. Actual isolated
  **Pydantic 2.10.0** compatibility run: **78 passed**, copied component tests only,
  without the application test conftest. Only `/tmp` dependency/cache directories
  were used; the owner's `.venv` and settings were unchanged. The ordinary current
  environment uses Pydantic 2.13.5.
- Final backend non-integration regression: **713 passed, 398 deselected, 7.44s**.
  The existing Starlette/httpx deprecation warning remains. Earlier intermediate
  full/focused passes do not replace this final result.
- Whitespace and local Markdown target/anchor checks pass. Independent plan/code
  reviews found no unresolved blocking issue after the provenance and dependency
  corrections. No frontend runtime code changed, so no new browser/UI result is
  claimed. Current schema/provider/queue behavior is unchanged.

Reproduce from the repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_curriculum_contracts.py
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend -m "not integration" --tb=short
git diff --check
```

The first slice was a pure internal foundation. It did **not** authorize membership, resolve
concurrent deletion, establish semantic support/solvability or deliver generated
assignments. The repository slice must reauthorize and revalidate dependencies
under a transaction fence with tenant/project composite keys and complete derived-
text deletion. That first slice introduced no API, migration, persisted curriculum
row, worker, model call, new dependency, owner-data mutation or running-service change.
No assignment quality, full Sprint 5 or full Alpha 2 approval is implied.

## Step 2a — immutable saved tutorial contexts (2026-10-29)

Starting worktree was clean at `65a8be4`. The exact commit's
[CI run 40862001849](https://github.com/emredemirbas/multimodal-rag/actions/runs/40862001849)
completed successfully in all four jobs; it certifies that earlier boundary,
not subsequent context code before its own hosted run.

Delivered:

- Migration `0020_curriculum_contexts.sql`, `curriculum/persistence.py` and
  `repository.py`: scoped immutable request/preferences and authoritative copied
  evidence, plus composite source dependency keys. No global learner default.
- Authenticated create/read/delete under
  `/api/v1/projects/{project_id}/curriculum/contexts`. Source pins/preferences
  are input; tenant/project scope, segment text and provenance are server-owned.
  Same input/key returns the same context, source order is canonicalized, changed
  input conflicts. Archive permits read/replay/delete but blocks new capture.
- Membership is rechecked/locked after identity mapping; project and selected
  source locks fence commits, publication and deletion in the same transaction.
  The unchanged local identity bootstrap can re-enroll membership on a later
  authentication; these repository tests do not claim persistent identity revocation.
- Capture all selected-generation segments with exact existing ASR/visual
  identities, text and filename, or reject the entire request. Retained old
  generations and legacy generation-one evidence without `processing_versions`
  remain valid. Existing managed visual provenance still fails closed.
- JSON wire limit 16,384 actual bytes, authentication before body consumption,
  duplicate-key/nonstandard-constant rejection, strict booleans/numbers and unknown
  field rejection. All curriculum responses, including errors, carry private/
  no-store, nosniff and same-origin resource headers. Logs expose IDs/counts only;
  HTTP metrics use route templates, without source/request/model content.
- Existing <=500-segment/500,000-character/per-segment bounds plus a
  4,000,000-byte serialized snapshot cap. Overflow rejects without truncation or
  partial records. These are resource bounds, not semantic/coverage/prompt limits.
- Deleting any selected source removes the whole multi-source context, copied
  text, dependencies and replay state. Project deletion cascades all new rows.
  No object-storage or private staging artifact was introduced.

Checks:

- **23 repository integration tests passed**: actual durable/legacy evidence,
  retained generations, exact OCR/mixed-description projections compared with
  existing evidence inspection, concurrent replay/conflicts, both scopes,
  archive, constructed/mutated inputs, overflow and complete deletion. Source
  deletion and membership revocation verify actual PostgreSQL lock waits.
- **15 real PostgreSQL + HTTP tests passed**: create/read/delete and replay,
  authentication/foreign scopes, stale/forged/pending pins, copied snapshot
  immutability, strict JSON, overflow, deletion and private errors/logs/metrics.
- **18 HTTP boundary tests passed**: chunked wire bytes despite a false content
  length, authentication before reads, exact-limit replay, ambiguous/invalid JSON,
  disconnect and private headers on success/error/read/delete paths.
- **5 database/migration tests passed**, including the populated 0019 -> 0020
  upgrade/repeat preserving existing RAG answers/citation identity, fresh and
  legacy Sprint 0 upgrades, checksums and project scope.
- Backend non-integration regression: **731 passed, 437 deselected, 8.06s**.
  The existing Starlette/httpx deprecation warning remains.
- The broad PostgreSQL run initially had **426 passed, 10 skipped, 1 failed**:
  an old visual-checkpoint migration test enumerated only files through 0019.
  Its expected additive list now includes 0020. Final full group rerun:
  **427 passed, 10 skipped, 731 deselected, 146.70s**; the same existing warning.
  The ten skips require separately opted-in real worker/service fixtures; these
  context tests require no Redis/MinIO/native model service.
- Independent code review found no unresolved blocker. No frontend runtime code
  changed and no new browser/build result is claimed.
- Final whitespace check passed. README stayed unchanged; internal delivery
  records and the next step remain in `docs/`.

All PostgreSQL checks used a new disposable container from the already-cached
`pgvector/pgvector:0.8.6-pg16` image, a random loopback port and a tmpfs database,
with synthetic data and isolated schemas. Parallel initial test runs exposed
fixture ownership of the shared vector extension in a temporary schema; anchoring
that extension in `public` in this disposable database resolved it. No application
migration or owner database needed a workaround. The mixed-description fixture
correctly yields four evidence segments for two frames; the capture preserves all
four rather than conflating frames with segments.
The labelled disposable container was stopped/automatically removed after checks;
its tmpfs database was discarded. Existing application services were left running.

Reproduce against a disposable database with vector already installed in `public`:

```bash
PYTHONPATH=backend TEST_DATABASE_URL='<disposable PostgreSQL DSN>' \
  backend/.venv/bin/python -m pytest backend -m integration --tb=short
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend -m 'not integration' --tb=short
git diff --check
```

No owner `.env`, model installation, credentials, Compose settings or running
application service was changed; migrations were applied only to the disposable
database. No new dependency, model call, generation/coverage/edit/activation
behavior or runtime permission default was introduced. Stored permission flags
do not settle the still-pending product policy or enable document retrieval.

## Step 2b — versioned editable drafts (2026-10-29)

Starting worktree was clean at `e51f819`; Git/CI were checked rather than inferred
from the prior handoff. At the last check,
[run 40867569194](https://github.com/emredemirbas/multimodal-rag/actions/runs/40867569194)
had passed backend tests, backend integration and frontend, while its images job
was still running. A running job is not a successful full run.

Delivered:

- Migration `0021_curriculum_drafts.sql`: scoped draft headers, append-only content
  revisions and project-scoped durable command receipts, all cascading from the
  immutable saved context. Receipt foreign keys identify the accepted revision.
- Shared strict `AssignmentContent` fields/validators, with server-owned scope
  added by `AssignmentDraft`. The HTTP DTO explicitly parses UUID text without
  enabling numeric coercion or accepting client scope/authoritative evidence.
- Create, latest/exact-revision read, optimistic full replacement and whole-draft
  delete API. Each revision versions the existing objectives, requirement labels,
  stable evidence references and acceptance/rubric/hint relationships. No extra
  standalone coverage score/CRUD or whole-tutorial extraction claim was invented.
- Every new content revision binds against the saved context inside the scoped
  transaction. Only cited authoritative projections leave the repository; source
  labels, times and processing versions cannot be supplied by the client. The
  revision stores content; evidence is resolved from its immutable context rather
  than duplicated into every content row.
- Membership/project/context deletion fences, atomic revision/receipt/head update,
  and a canonical hash of operation/target/expected revision/content. A matching
  retry returns its original accepted revision after later edits or archive;
  response metadata does not change to the latest head. Reusing a key for changed
  input/target/operation conflicts. A stale edit with a new key leaves no receipt.
- Archive permits history, replay and delete; new create/edit is blocked. Deleting
  draft/context/any selected source/project removes all dependent content and
  receipts, including dependencies unused by the draft's citations. A retained
  context keeps its original generation/filename/provenance after reprocessing.
- Context row locks fence direct source deletion's cleanup trigger without taking
  source locks in the opposite order. Existing local identity bootstrap behavior
  is unchanged; repository membership locking is not persistent identity revocation.
- Draft wire limit 272,384 bytes, context wire limit still 16,384; normalized scoped
  draft limit 256,000 UTF-8 bytes and spaced JSONB content limit 300,000 bytes.
  Reject actual NUL text before PostgreSQL with a safe 422; preserve literal
  escape text. All responses stay private/no-store, nosniff and same-origin.
  Logs/metrics carry IDs/revisions/counts/route templates, not content/request keys.

Actual checks:

- **29 repository integration cases passed**: historical command replay,
  concurrent same-key create/edit and competing stale edits, both scopes/actors,
  archive, reference/effort/permission/constructed input failures, atomic rollback,
  byte cap/NUL handling, retained evidence, full cascade and actual PostgreSQL
  dependency/membership lock waits.
- **16 PostgreSQL + HTTP integration cases passed** in **6.69s**: scoped lifecycle,
  exact revision reads, historical/archive replay, stale edit recovery, strict
  JSON/UUID/numbers/unknown fields, forged metadata, deletion and private logs.
  The source-delete case invokes the authoritative DB trigger directly because
  its fixture has no object store; draft/context/project deletion uses actual API.
- **101 focused contract/boundary tests passed** (78 existing domain cases and
  23 HTTP boundary cases), including unchanged context limits and exact/over-limit
  draft chunked input with authentication before reads.
- **61 PostgreSQL/migration and existing visual-checkpoint cases passed**. Fresh/
  legacy upgrades and populated pre-0020/pre-0021 upgrades preserve existing RAG
  citation identity and immutable saved context. Repeated migrations/checksums
  are verified; both historical explicit migration enumerations include 0021.
- Backend non-integration regression: **736 passed, 483 deselected, 8.67s**.
  The existing Starlette/httpx deprecation warning remains.
- Final broad PostgreSQL integration: **473 passed, 10 skipped, 736 deselected,
  189.92s** with the same existing warning. The ten skips require separately
  enabled real worker/object-store fixtures; no owner services were used.
  No browser/frontend code changed and no new UI/build result is claimed.
  Independent read-only code review found no unresolved blocker.
- Final whitespace check passed. README was unchanged; sprint/status/CI records
  remain in `docs/`.

All database work uses a new labelled disposable container with the cached
pgvector image, a random loopback port, tmpfs data and vector installed in public
before parallel isolated-schema tests. No owner `.env`, database, credentials,
Compose configuration, models or running application service was changed.
The labelled disposable container was stopped/automatically removed after tests;
its tmpfs database was discarded.
No new dependency/model call, automatic generation, activation, code execution or
deadline/tutoring behavior was introduced. With no authorized documentation
snapshots yet, external/document requirements fail binding; this does not confirm
either pending product-policy choice or certify semantic support/solvability.

## Step 3a — internal durable runs and progress (2026-10-29)

Starting worktree was clean at `8a5a847`. Its exact
[CI run 40869469607](https://github.com/emredemirbas/multimodal-rag/actions/runs/40869469607)
was rechecked: all four jobs completed successfully. This establishes the prior
baseline, not the new code's hosted result before push.

Delivered:

- Migration `0022_curriculum_runs.sql`: six context/project-owned tables for runs,
  attempts, outbox, command receipts, private checkpoints and local model-call
  attribution. All keys/queries are tenant/project scoped, with context deletion
  cascades. No synthetic ingestion source or source generation change.
- Internal strict run/progress contracts, `RunRepository` and
  `RunProgressRepository`. Create atomically accepts an explicit saved context and
  workflow version with its own outbox row. Scoped read/cancel/manual retry,
  exclusive claim, heartbeat, bounded automatic retry and expiry recovery exist.
  There is no HTTP producer, queue/scheduler wiring, provider call, success state
  or generated-draft publication in this slice.
- Worker authority is loaded from the stored original actor/context, not supplied
  by a claim. Membership -> project -> context -> run locks prevent scope/deletion
  races without reversing the direct source cleanup order. Wall-clock lease checks
  after lock waits prevent expired heartbeat resurrection. Archive/revoked original
  membership terminally block work and close started calls. Existing identity
  bootstrap semantics remain unchanged.
- Fresh token per attempt, 180-second lease, three automatic failures and a
  five-second retry delay. Explicit original-actor retry resets the failure budget
  while retaining accepted private state. Command receipts replay the accepted
  cancel/retry state even after later state changes. Outbox changes are atomic;
  no broker publication/delivery is claimed yet.
- Sequential immutable checkpoint identities, workflow/stage/attempt metadata,
  hash and bounded JSON. Maximum 64 checkpoints, 300,000 compact UTF-8 bytes and
  327,680 actual JSONB bytes each. The hash uses compact values normalized as
  JSONB will return them. Private generic state is not semantic validation or
  published tutorial evidence.
- Before-invocation physical-call metadata identity, model/digest/engine/prompt
  version, counts and immutable accepted completion data. The start fingerprint
  covers declared metadata, not exact prompt bytes. At most 256 call records/run;
  a new physical attempt needs a new call ID. Unknown usage/duration stays null,
  actual zero stays zero, and database-constrained local spend is zero. Interrupted
  attempts close started calls without inventing results. Tests use synthetic
  declared/returned counts and never invoke an actual model.
- Deleting any selected source/context/project removes all new private text,
  receipts and usage, including unused source dependencies. Stale claims cannot
  restore deleted/cancelled/expired work. Event logs contain IDs/status/stage/counts,
  never private payload, credentials or request keys.

Actual checks:

- **31 lifecycle PostgreSQL cases passed**: create/command replay and conflicts,
  scopes/original actor, concurrent claims, lease expiry during an actual project
  lock wait, cancellation, retry budget/recovery, archive/revocation, atomic fault
  rollback and complete dependency cascades.
- A constructed/mutated boolean regression exposed JSON serialization converting
  a forged integer `True` into `1`. Strict Python-value reconstruction now keeps
  the original type and rejects the bypass. The initial failing case passed after
  the correction; progress DTO validation uses the same strict approach.
- **67 progress PostgreSQL cases passed**, **27.67s**: checkpoint ordering/replay,
  payload/storage limits, concurrent writers, actual rollback after insert,
  metadata/finish receipts, call limits, NULL versus zero, retry preservation,
  stale/foreign tokens and complete private state removal.
- Independent review found JSONB numeric normalization was not covered by Python
  JSON size/hash preflight. Three added tests **failed before the fix**: finite
  `1e308` exponent expansion reached an unsafe constraint error, while loaded
  `1e20` and negative zero caused false replay conflicts. Actual JSONB size is now
  checked before INSERT/oversized value transfer, normalized values are bounded
  again and hashed/stored. All three regressions passed, followed by the full
  67-case progress run. NUL/non-finite JSON is also safely rejected.
- **7 database/migration cases passed**: fresh/legacy install, checksums/repeat and
  populated pre-0020/pre-0021/pre-0022 upgrades preserve RAG citation identity,
  saved contexts, draft history and accepted edit replay. Both historical migration
  enumerations include 0022; the six new tables start empty on upgrade.
- Backend non-integration regression: **736 passed, 582 deselected, 7.60s**.
  The existing Starlette/httpx deprecation warning remains.
- Full PostgreSQL integration: **572 passed, 10 skipped, 736 deselected,
  202.53s** with the same existing warning. The ten skips require separately
  enabled real worker/object-store fixtures. Independent review found no remaining
  blocker after the numeric correction. No frontend/browser/image rebuild result
  is claimed for this slice.
- Final whitespace check passed. README was unchanged.

Checks use a new labelled disposable PostgreSQL container from the cached image,
random loopback port and tmpfs data, with vector in public and isolated synthetic
schemas. No owner `.env`, credentials, database, Compose setting, model installation
or running application service was changed. No new dependency or model download.
The labelled disposable container was stopped/automatically removed after tests;
its tmpfs database was discarded. Existing application services stayed running.
These tests simulate repository leases and failures; real worker/process loss,
broker outage/redelivery and final draft publication remain step 3b work. Full
Sprint 5, generation quality and the independent real-video Alpha 2 review remain
open. README remains product documentation without these delivery details.

## Step 3b — separate delivery and atomic publication (2026-10-29)

Started from `b6f9096` with its exact
[CI run 40877097378](https://github.com/emredemirbas/multimodal-rag/actions/runs/40877097378)
rechecked: all four jobs completed successfully. An interrupted work session was
resumed from its existing uncommitted files rather than replacing them.

Delivered:

- Additive migration `0023_curriculum_delivery.sql`: succeeded runs,
  checkpointed/succeeded delivery attempts and a scoped exact-revision result
  relation. Applied 0022 is unchanged. Deleting a generated draft removes the
  pointer but preserves terminal run history; dependency deletion cascades all
  private/result state. A later user edit does not move the original result.
- A separate Celery task/queue, optional `curriculum-internal` Compose worker and
  Docker target. One process slot, 90/120-second soft/hard limits below the
  180-second lease, read-only filesystem and bounded resources. Normal startup
  omits this profile. It needs migrations/Redis and has no model or object-store
  dependency, shared object credentials, mounted user data or exposed port.
- Independent scoped outbox dispatch, publication retry, sent/unclaimed rearm
  after 60 seconds and bounded expired-run recovery in the scheduler. Broker calls
  happen outside transactions; token-conditioned ACKs cannot overwrite a fast
  worker's next checkpoint delivery. Logs contain safe IDs/counts/failure codes,
  never broker exception text, model/source payload or credentials.
- A detached stage input with original authorized run/context/checkpoints and a
  private claim for before-invocation call attribution. One trusted bounded stage
  runs per delivery outside DB locks. Its result is either a new sequential
  checkpoint or final strict content; call attribution must finish before either
  can be accepted. Unexpected adapter failures consume the bounded failure budget
  and interrupt open calls without inventing usage.
- Checkpoint, attempt closure, pending state and outbox reset commit atomically.
  Continuation gets a fresh token/attempt and preserves the failure budget. A
  duplicate old checkpoint cannot repeatedly yield without progress.
- Final publication revalidates strict content, reconstructs server-owned scope
  and binds exact saved evidence under the current authority/context/live lease.
  New draft/revision/result, successful attempt/run and outbox removal share one
  transaction. No fake user command key or second repository connection is used.
  Wall time is checked again after the last outbox write; expiry during that write
  rolls back every output/status change.
- The application processor registry remains empty. Unknown versions fail
  explicitly with `processing_unavailable`; there is no environment-selected
  processor import, fixture generator or public run-create/generation endpoint.
  Synthetic processors exist only in tests. No model is invoked or downloaded;
  LangGraph/local provider work remains step 4.

Actual checks:

- **57 focused integration cases passed, 24.05s**: 43 delivery/persistence cases,
  five dispatcher cases, seven test-adapter execution cases and two actual Celery
  SIGKILL boundaries. Covers strict/binding failures, scopes, cancellation,
  archive/revocation, dependency deletion, no lock during processing, concurrent
  publication, exact result/history, atomic fault rollback and fresh wall-clock
  checks after project-lock waits and final outbox writes.
- Actual worker tests kill only their owned subprocess: before final output
  commit, lost work is recovered/recomputed with one failure; after checkpoint
  commit/before acknowledgement, the saved stage is reused without spending a
  failure. Real Redis duplicate deliveries are consumed before a FIFO barrier;
  one draft/revision/result remains. This is delivery recovery evidence using a
  labelled fixture adapter, not native model generation or quality evidence.
- The first focused run exposed an unordered SQL-result assumption in a test.
  Assertions now compare attempt identities/statuses explicitly; all 57 pass.
- **7 focused database/upgrade cases passed, 2.17s**. Populated pre-0023 migration
  preserves existing RAG citations, context/draft history, running attempt,
  accepted checkpoint and unknown call usage. Fresh/legacy and earlier curriculum
  upgrades pass; both historical migration enumerations include 0023.
- The first broad run failed when the disposable database's 768 MiB tmpfs filled
  with WAL. It is not an application pass. Only that test container was replaced
  with 2 GiB tmpfs and a bounded WAL setting before repeating the full suite.
- Final backend non-integration regression: **736 passed, 640 deselected, 8.11s**.
- Final full PostgreSQL/Redis integration: **630 passed, 10 skipped, 736
  deselected, 247.77s**. Both actual curriculum worker probes passed. The ten
  existing skips require separately enabled media worker/MinIO fixtures.
  The existing Starlette/httpx deprecation warning remains in both suites.
- The final curriculum worker Docker target built successfully. A network-disabled,
  read-only disposable container verified task registration, separate queue,
  90/120-second limits and the empty processor registry. Compose profile/resource/
  dependency checks used explicit synthetic values with `--env-file /dev/null`.
  No frontend runtime code changed; no new local UI/browser result is claimed.
- Whitespace and changed Markdown local-link checks passed. README is unchanged;
  current status and the concrete next step are recorded in delivery/plan docs.

Tests used only labelled disposable cached PostgreSQL/Redis containers, random
loopback ports, synthetic schemas, unique Redis prefixes and owned subprocesses.
Both test schema count and Redis key count were zero after the final suite. The
test containers and temporary worker image tag were removed after verification.
No owner `.env`, credentials, real database/data, installed model or running
application service was changed. The new Compose worker is an optional repository
definition; it was not started in the owner's application stack.
This completes the selected delivery slice, not Sprint 5 generation/quality/UI
acceptance or the independent real-video Alpha 2 review. Check the exact pushed
commit's hosted workflow separately; the verified starting CI alone does not
certify this implementation.

## Continuation

Next: step 4 in `implementation-plan.md`, the application-owned local provider and
bounded LangGraph workflow. Start with read-only inventory of already installed
local model/engine identities and explicit prompt/stage budgets. Do not download
weights or enable public generation prematurely; the current registry is empty.
Preserve source/context scope,
original actor, exact command replay and complete deletion; no synthetic source.

Resolve the pending extension and official-document policy before enabling their
dependent behavior. Preserve source-generation pins, no paid calls/downloads,
complete deletion and the separation from later submission/grading/tutoring work.
Verify the exact new commit's hosted CI after push; the green starting baseline
alone does not certify subsequent implementations.
