# Sprint 5 — validation record

Date: 2026-10-29. Status: internal contracts, saved contexts, versioned draft APIs
durable queued delivery/atomic draft publication and the pinned local JSON/call
provider foundation implemented. Model
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

## Step 4a — pinned local provider and call attribution (2026-10-29)

Started from a clean `22fa629`. Its exact
[CI run 40894724175](https://github.com/emredemirbas/multimodal-rag/actions/runs/40894724175)
was rechecked: all four jobs completed successfully. Step 4 was split into the
provider/receipt foundation here and prompts/batching/LangGraph in 4b to keep the
boundary reviewable. The two product-policy questions were surfaced again; no
answer was inferred from `devam` or from elapsed time.

Read-only local inventory (no inference/install):

- Pre-existing `qwen3:4b`, digest
  `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`.
- Ollama 0.40.3; family `qwen3`, completion capability and no remote-model/host
  fields. The existing embedding model was also present but is not used here.
- Inventory used only list/version and tags/show/version requests. This observed
  identity is not a compiled default, new approved-model list or native-quality
  result. Constructor callers must provide an explicit full digest and engine pin.

Delivered:

- `LocalCurriculumProvider`, an application-owned JSON provider separate from
  chat's short answer schema. Prepare a detached bounded request, hash its exact
  serialized JSON body, verify local model/engine identity before and after the
  request and reject drift. Fixed text-only roles/options, no proxies/redirects,
  tools, thinking, arbitrary endpoint, external schema `$ref`, cloud fallback or
  install/pull request. Errors and representations exclude private text.
- Fixed resource bounds in the implementation plan: combined UTF-8 text, schema,
  request, response and output bytes; context/output-token/thread configuration;
  metadata/inference socket timeouts and a shared acceptance deadline. Deadline
  checks reject late output, while the existing Celery process limits remain the
  ultimate bound for blocked I/O. No byte count is called a tokenizer estimate.
- Strict JSON decoding rejects duplicate keys at all depths, non-finite numbers,
  invalid UTF-8/surrogates/NUL, arrays instead of objects, truncation and ambiguous/
  oversized HTTP envelopes. Require complete assistant output with stop reason,
  the pinned model and valid nullable usage. Schema formatting does not establish
  application-schema compliance, source support, feasibility or quality; the
  later graph must run deterministic contract/evidence binding before publishing.
- `LeasedCurriculumCalls`: commit the scoped start receipt before physical
  inference, perform no HTTP call if admission/commit fails, invoke outside DB
  locks and finish actual usage under the fresh lease before returning output.
  Unknown usage remains null; actual zero remains zero; billed spend stays zero.
  Started failures retain validated available usage, safe codes and actual request
  duration. Interrupted/revoked/deleted work cannot deliver a late response.
- Additive migration `0024_curriculum_request_identity.sql` and strict call
  metadata: exact body `input_sha256`, `schema_version` and `request_version`,
  all present or absent together. Historical metadata-only rows stay null and
  keep their original replay fingerprint. Reusing a call key for changed body or
  versions conflicts. No raw prompt/schema/response is put into usage rows.
- Start/finish receipt writes check wall time again after writing. Expiry during
  an actual delayed INSERT/UPDATE rolls back the receipt, preventing inference or
  output return; lost work can still be retired by existing recovery.
- No HTTP generation endpoint, processor registration, LangGraph dependency,
  application prompts, coverage extraction, activation or UI is enabled. No
  source generation/evidence ID is changed. External-doc policy remains pending
  and no document fetch is introduced. README and existing runtime settings remain
  unchanged.

Actual checks:

- **50 local HTTP cases** are included in the final unit suite: exact request/
  identity pinning, pre/post drift, no proxy/redirect/download/tool behavior,
  strict JSON, byte/time caps, huge Content-Length, private errors/representations,
  capacity/admission and null versus zero counts. All responses are authored;
  no installed model receives a generation request.
- **100 focused PostgreSQL/HTTP/migration cases passed, 43.13s**, including 24 new
  leased-call cases and the existing progress/migration suite. Covers receipt
  commit before HTTP, atomic commit failure, no DB lock during inference, original
  authority/scopes, concurrent cancellation/deletion/revocation/archive/expiry,
  final-write expiry rollback, actual failed-call usage and immutable replay.
- Populated pre-0024 upgrades preserve existing RAG citations, contexts, draft
  history, running state/checkpoints and old metadata-only start receipt replay.
  Fresh/repeated/checksum and earlier upgrades remain covered. Both historical
  migration enumerations include 0024.
- Final backend non-integration regression: **786 passed, 665 deselected, 9.49s**.
  The existing Starlette/httpx deprecation warning remains.
- Final full PostgreSQL/Redis regression: **655 passed, 10 skipped, 786
  deselected, 281.47s**. Both real curriculum worker/process-loss probes passed;
  the ten existing skips require separately enabled media-worker/MinIO fixtures.
  The same existing deprecation warning remains.
- A direct worker import verified that `PROCESSORS` remains empty; component
  implementation does not enable public generation. No frontend/Docker config
  changed and no new local browser/native-generation result is claimed.

Official API behavior was checked against the
[Ollama chat API](https://docs.ollama.com/api/chat) and
[structured-output guide](https://docs.ollama.com/capabilities/structured-outputs).
The [LangGraph workflow guide](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
informs 4b only; no hosted tracing/service or model dependency is activated here.

Checks used cached, labelled disposable PostgreSQL/Redis containers with random
loopback ports, tmpfs data, public pgvector and isolated synthetic schemas/Redis
prefixes/worker processes. Test schema count and Redis key count both ended at
zero; both labelled containers were removed after verification. No owner `.env`,
credentials, database/data, model installation or running service configuration
was changed. Only read-only inventory requests reached the existing model service;
all inference responses came from test HTTP servers. Whitespace/local Markdown
target checks passed, and README is unchanged. The exact new commit's hosted
workflow must be checked separately from the green starting baseline.

## Internal objective extraction and LangGraph workflow (2026-10-29)

Starting checkout/origin was clean at `6407ca4` (pinned provider/call attribution).
Its exact [CI run 40906315963](https://github.com/emredemirbas/multimodal-rag/actions/runs/40906315963)
was rechecked: it was initially still running, then all four jobs completed
successfully before this commit. Its success does not certify the new change.
Pending extension/document-policy answers remain pending; `devam` is not an answer.

Delivered step 4b as an internal component:

- Pinned `langgraph==1.2.18`; actual `StateGraph` nodes perform model ->
  deterministic validation -> checkpoint or publication. The existing Celery
  queue, scoped lease/call ledger and database checkpoints own delivery/recovery.
  No library checkpointer, environment change or hosted tracing is introduced;
  `tracing_context(enabled=False)` covers compilation/invocation and node threads.
- Tutorial-only eligibility requires all three external-topic/document flags
  explicitly false. A true flag fails before inference, without choosing a
  permanent product policy. Default worker registry remains empty; no public
  generation/run producer, activation, external fetch or UI is enabled.
- Lossless Unicode slicing retains original segment/source/processing identity
  and exact character offsets. <=1,800 UTF-8 bytes/slice, four slices/batch,
  20 batches; excessive input fails before any call. No prefix truncation or
  silently selected subset of source text. Existing context bounds still apply.
- Each extraction has <=2 goals, exact nonempty quotes in named slices and
  supported/insufficient-evidence coverage for every slice. ASR/OCR/description
  origins are explicitly unreviewed. Quote membership and relationships are
  structural checks; model-reported support is not verified semantic entailment.
- Select <=4 known goals from <=40, preserving all extracted goals/coverage and
  the selected subset in private progress. Unselected material is omitted from
  the assignment, not reported as fully covered. Drafts must copy selected
  objectives exactly and use all of them with consistent covered tutorial links.
  Existing schema, effort, permission and authoritative evidence binding remain
  mandatory; publication rebinds under the database fence.
- First delivery pins context/recipe/plan/model identity without inference.
  Each later delivery makes at most one physical call. Resume validates scope,
  sequence, payload hash, context/recipe/plan/provider identity and each legal
  transition before inference. Accepted extraction/selection is reused after loss.
- Invalid extraction/selection fails safely. Invalid draft gets at most one
  bounded revision with a fixed feedback code; oversized proposal/prompt fails
  without truncation. At most 23 checkpoints/23 workflow calls, apart from the
  existing bounded transient retries. Lost admission/finish discards work without
  adding a failure or allowing stale progress. No schema migration is needed:
  private text uses the existing context-owned checkpoints/deletion cascades.

Actual checks:

- **50 graph/objective unit cases passed, 7.04s**: lossless multibyte/escaped text,
  overflow before calls, exact identities/offsets, ASR and visual origin labels,
  UTF-8 caps, invented quotes/IDs, incomplete/ambiguous coverage, selection,
  explicit omissions, strict scope/pin/progress replay, invalid/transient/late
  output, one repair and a maximum-size plan with exactly 23 calls/checkpoints.
  Graph construction is repeated between deliveries; no in-memory continuation
  is required. Env-enabled tracing is tested with hosted client creation forbidden.
- **17 focused PostgreSQL/HTTP/real-worker cases passed, 17.35s** after final
  recipe pinning. Fourteen exercise the real graph with authored HTTP inference:
  detached checkpoint resume, one bound result, physical-call receipts, failed
  JSON repair attribution, invalid revision, transient retry and cancellation/
  archive/revocation/expiry/source/project deletion during unlocked inference.
  Wrong tenant/project/run cannot start the graph or contact HTTP.
- Three actual Celery process probes passed, including the two existing generic
  delivery boundaries and the new graph extraction boundary: SIGKILL after the
  accepted extraction commit, replacement selects/generates without extracting
  again, two duplicate tasks consumed before a FIFO barrier, one draft/revision/
  result and exactly three physical calls. Only owned test processes are killed.
- Final backend non-integration regression: **836 passed, 680 deselected, 16.19s**.
- Full PostgreSQL/Redis regression: **670 passed, 10 skipped, 831 deselected,
  276.96s**. The ten existing skips require separate media-worker/MinIO opt-ins.
  Five subsequently added unit boundary cases were run in the final unit suite;
  final graph/integration focused reruns passed as recorded above.
- Fresh worker image built from `backend/Dockerfile` target `curriculum-worker`.
  With networking disabled/read-only filesystem and both tracing env flags true,
  it imports pinned LangGraph, compiles the graph without a checkpointer and
  reports an empty default registry. No model/database request is made by this
  smoke. `uv pip check` found all 75 temporary-environment packages compatible.

All inference replies in these tests are authored; no actual model generation,
native quality, semantic coverage, feasible difficulty or exercise solvability
has been reviewed. No installed weights were downloaded/replaced, no owner model
received an inference request and no paid endpoint was used. The independent
owned/licensed real-video quality gate stays open. README is unchanged.

Tests used a separate temporary Python environment, cached labelled disposable
PostgreSQL/Redis containers with random loopback ports/tmpfs, isolated schemas,
random Redis prefixes and owned worker processes. Schema count and Redis key
count ended at zero; both test containers and the temporary worker-image tag were
removed. Owner `.env`, credentials, Docker configuration, data and running
services were not changed. The exact new commit's CI must be checked after push;
local results do not make a running hosted workflow successful.
Whitespace and changed Markdown local-target checks passed; README is unchanged.

## Native review, extraction-schema correction and confirmed policy (2026-10-29)

Starting checkout/origin was clean at `caaa619`. Its exact
[CI run 40911625107](https://github.com/emredemirbas/multimodal-rag/actions/runs/40911625107)
was initially still running; all four jobs completed successfully before this
commit. That is software validation, not native model-quality acceptance.

The owner explicitly confirmed tutorial-only by default with learner opt-in for
prerequisites/extensions, and learner selection/approval for each official
document before retrieval. Updated `07-open-decisions.md` and the plan; do not ask
these questions again or infer that generic opt-in authorizes automatic fetching.
Current true-flag rejection remains until approved capture is implemented.

Before inference, saved three new MIT-licensed authored VTT samples and explicit
expected goals, forbidden topics, learner settings and insufficient-evidence
behavior in `native-output-review.md`. These are text fixtures without a real
recording. Read-only inventory freshly verified existing local `qwen3:4b` digest
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, Ollama
0.40.3, family/capabilities and no remote identity. No weights were installed.

Used the actual application source processor, saved contexts, graph, scoped
physical-call receipts, checkpoints and binding against a disposable PostgreSQL.
The private test-only registry was passed directly to `advance_run`; there is no
new endpoint, evaluation service or shipped diagnostic tool. A one-off isolated
CLI runner was used, not the API or owner DB. No Celery recovery is claimed by
that runner; recovery has its separate real-process tests.

Native findings (**review did not pass**):

- Original profile: both supported examples timed out at extraction around
  42 seconds. Each failed receipt is `provider_timeout`, tokens remain unknown,
  and the probe stopped at `retrying` without automatic retries. The insufficient
  example returned no goals but an invented `s01000` slice ID; strict application
  validation rejected it as `invalid_output`, not a successful abstention.
- One predeclared <=55s streaming diagnostic used the same English prompt/schema/
  model/options, changing only stream delivery. It completed in 50.72s, first
  content at 19.97s; 652 input/391 output tokens, no thinking/tools. Output would
  still fail: non-null supported reasons and nonliteral quote/escape characters.
  It is diagnostic evidence, not an accepted application call or quality pass.
- Extraction prompt/schema v2 now constrains both anchor/coverage IDs to the
  supplied batch and encodes supported (`reason:null`, nonempty IDs) versus
  insufficient (`goal_ids:[]`, bounded reason) branches in structured decoding.
  Clarified local goal IDs, short literal quotes and single JSON escaping. Strict
  returned quote/reference/coverage/UTF-8 validation remains; no title-card keyword
  filter, relaxed grounding, deadline extension, new model or extra semantic judge.
  Existing payload shape/valid relationships remain; recipe/request hashes and
  prompt/schema versions change, preventing silent adoption by old pinned runs.
- Single corrective pass: both supported extractions still timed out. The
  insufficient text now yielded structurally valid but **semantically wrong**
  `supported` coverage: its “no learning goals can be derived” statement became a
  goal and was selected. Generation then timed out. No draft was published; that
  does not make the false-positive coverage correct. Supported draft quality,
  effort/language/hint quality and solvability remain unreviewed.
- **Nine actual native requests total**: 3 original, 1 diagnostic, 5 corrective.
  Full public sample output, request/recipe hashes, usage and failure receipts
  are in `native-output-results.json`. All runs stayed within their predeclared
  budgets. The default registry/public generation remain closed; no Sprint 5 or
  independent real-video/Alpha 2 quality approval is given.

Checks after correction:

- **57 focused graph/objective unit cases passed, 7.59s**. Seven new cases verify
  actual-batch native ID choices, schema-expressible status invariants and strict
  rejection of contradictory status/reason/ID values; existing quote, scope,
  progress, bounded repair and tracing checks remain.
- Full backend non-integration regression: **843 passed, 680 deselected, 26.00s**.
- **17 PostgreSQL/HTTP/real Celery worker cases passed, 24.48s**: actual graph
  checkpoints/publication, versioned call receipts, retries, lease/authority/
  deletion races and SIGKILL/duplicate recovery. These authored HTTP tests do not
  override the native failures. No database schema or frontend behavior changed.
- Fresh v2 worker image built; no-network read-only smoke verified prompt/schema
  v2 imports and the empty default registry. README remains unchanged.

All native samples were separate owned/licensed test data. Test project/context/
run/checkpoint/call rows and in-memory artifacts ended at zero; isolated test
schemas and Redis keys also ended at zero. Both labelled disposable test containers
and both temporary image tags were removed. The owner's nine running container
IDs were identical before/after; `.env`, credentials, application data, Docker
configuration and model installations were unchanged. Only explicit local
inference and inventory reached the pre-existing model service.

## Compact extraction profile v3 — 2026-11-11

Starting checkout was clean at `cc1da53`; its exact
[CI run 42501823081](https://github.com/emredemirbas/multimodal-rag/actions/runs/42501823081)
completed successfully in all four jobs. GitHub now reports the active repository
as public; the original email-bearing archive stays separate/private.

Implemented a bounded extraction change, with no provider/queue/lease limits or
database schema changes. Model messages contain explicit language plus local
slice ID/origin/lossless text; authoritative source/segment/generation/version/
offsets remain in context and batch maps. Exact context and recipe hashes prevent
different evidence or old v2 progress from adopting the compact request. The
shorter v3 prompt distinguishes demonstrated technical actions from absence/
announcements/limitations. Quote membership remains literal; quote validation is
now at most 80 UTF-8 bytes with an additional native 80-character ceiling.

Checks:

- **857 backend non-integration cases passed**, including 14 new resource/binding/
  replay regressions. Coverage includes all four origin labels, literal malicious
  text, correct segment/Unicode span when two sources repeat a quote, 80/81-byte
  ASCII/Turkish/emoji boundaries, identical model requests with different context
  identities, v2-recipe rejection, existing quote/status/coverage checks, transport
  timeout/late output and bounded recovery. An initial sandboxed HTTP-test run
  could not open sockets; the complete run with local-socket permission passed.
- **17 isolated PostgreSQL/HTTP/real Celery process cases passed, 19.22s**:
  exact v3 call receipts, detached checkpoints, one result, bounded revision,
  retry, scope denial, lease/cancellation/archive/revocation/deletion races and
  SIGKILL/duplicate-delivery recovery. Their model replies are authored fixtures.
- The predeclared **three actual local extraction calls** used unchanged installed
  `qwen3:4b`/digest/Ollama pins and 42/60-second limits. English was structurally
  accepted at 37.599s but missed the expected GET/list skills; Turkish timed out
  at 42.042s; the negative example at 29.197s still produced a supported meta-goal.
  **The native review failed.** Full output/usage and manual interpretation are in
  `native-extraction-v3-results.json` and `native-output-review.md`. No selection,
  generation or retry was attempted; zero drafts is not successful abstention.

The test environment used separate schemas, Redis prefixes/queues, owned worker
processes and cached disposable PostgreSQL/Redis/model containers on an internal
network. Temporary loopback relays exposed only those endpoints to the test
processes. Source/context/run cleanup and artifact deletion were exercised; schema
and Redis counts ended at zero. Test containers/network/relays were removed; owner
container IDs/running state, image IDs and volume names were identical before/after.
Existing owner services stayed stopped. No new image was built/downloaded, weights
were read-only, and no `.env`, credential, owner data or Docker setting changed.
README is unchanged; no frontend test/build or default enablement was needed.

## Compact model wire and application-owned normalization — 2026-11-11

Starting checkout/origin was clean at `b0230ee`. Its exact
[CI run 43056602011](https://github.com/emredemirbas/multimodal-rag/actions/runs/43056602011)
had successful backend, integration and frontend jobs; the image job was still
running at the checks in this continuation. No full success is assumed.

Implemented v4's dedicated `CompactExtraction` model wire: goals have only
description/anchors, and each unanchored slice needs an explicit insufficient
ID/reason. Native schema presents goals before insufficiency even under the
provider's sorted JSON. The application assigns `goal0`/`goal1` and reconstructs
the existing batch-ordered `BatchExtraction` checkpoint. Missing/foreign/duplicate
insufficiency, anchored/insufficient contradictions, duplicate anchors and exact
duplicate goals (including reversed anchor order) fail without repair or fallback.
Distinct goals may share evidence; one goal may span two slices.

Recipe pins wire schema, normalized schema and `compact-extraction-map-v1`.
Replay revalidates application-owned IDs and coverage order; old v3 progress and
old wire responses cannot silently adopt v4. Complete source/context pins, literal
quotes, UTF-8 bounds, scoped call receipts, live actor/lease/deletion fences and
one-call-per-delivery behavior remain. No schema migration, provider/queue timeout,
worker registration, HTTP capability, frontend or README change was needed.

Actual checks:

- **903 backend non-integration tests passed, 17.49s**; **684 deselected**.
  The new 46-case wire suite covers strict partitions, shared/multiple anchors,
  empty goals, duplicate/nonstandard JSON, foreign/model-owned fields, repeated
  goals, quote/description/reason byte boundaries, post-parse mutation, repeated
  source text with distinct Unicode spans, canonical-ID/order tampering and
  v3/mapping-version replay fences. A focused final run after the serialized-schema
  assertion also passed **46 tests, 1.43s**.
- **21 PostgreSQL/HTTP/real Celery process cases passed, 20.01s**. Four added cases
  prove invalid compact responses cannot commit extraction/draft, and explicit
  empty goals persist canonical insufficiency then stop before selection. Existing
  receipt metadata, retries, scoped authorization/deletion/lease races and SIGKILL/
  duplicate recovery pass. The recovered graph retains application goal IDs and
  canonical coverage. HTTP/model delivery success is distinct from stage acceptance.
- The declared **three native extraction calls** used unchanged installed
  `qwen3:4b`/full digest/Ollama pins and 42/60-second limits. English timed out at
  42.042s; Turkish returned at 40.509s with nonliteral quotes and contradictory/
  duplicated insufficiency; the negative at 24.118s still made a meta-goal and
  contradicted it with insufficiency. **The native review failed.** All retained
  only initialization checkpoints; no extraction checkpoint or draft was accepted,
  and selection/generation was not attempted. Exact public-sample
  output/usage and manual interpretation are in `native-extraction-v4-results.json`
  and `native-output-review.md`. Rejection is not correct semantic abstention.

The tests used isolated schemas, random Redis prefixes/queues and owned processes
with cached disposable PostgreSQL/Redis/model containers on an internal network.
Temporary loopback relays exposed only test endpoints; weights were mounted
read-only. Source/context/run/artifact cleanup and schema/key cleanup ended empty;
all test containers/network/relays were removed. Owner container/running state,
image IDs and volume names were identical before/after. Existing owner services
stayed stopped. No image build/download, model install, `.env`, credential, data
or Docker setting change occurred. The default registry remains empty; neither
software tests nor this failed native pass enable user-facing generation.

## Step 5a — explicit official-document approval and capture API (2026-11-11)

Starting state was rechecked on clean `main` at
`532197b6acf864e6b4ad150e83a2b29a8671d36b`, matching GitHub. In its
[CI run 43060500398](https://github.com/emredemirbas/multimodal-rag/actions/runs/43060500398),
backend tests, backend integration and frontend succeeded; the image job was
still running at the last pre-commit check. That is not overall CI success and
this new commit requires its own hosted result.

The existing Step 5 was split into backend capture (5a) and learner selection/
approval UI (5b). The implementation is independent of the failed native model
review and does not register a processor or enable external-topic generation.

Implemented:

- Migration 0025 adds project/context-owned approval, capture-command and immutable
  snapshot tables with composite scope keys and cascading dependencies. Explicit
  consent, original approver/time and complete catalog policy are retained. Contexts
  must allow external documentation. Approval/read/list perform no network I/O;
  a separate capture command is restricted to the original approving member.
- The application-owned catalog contains one exact English FastAPI First Steps
  route. Its MIT license was verified against the
  [official license](https://github.com/fastapi/fastapi/blob/master/LICENSE), Git
  blob `3e92463e6bd522a2a21e5f0a80d8089d6c4be20d`; the full notice and attribution
  are retained with every policy. The unversioned page has `detected_version=null`.
  No live lesson page was fetched during development or validation.
- Production fetching checks every DNS result, rejects nonpublic/transition
  addresses and pins the selected numeric socket for verified original-host TLS.
  No user URL, redirect, proxy, credentials, compression, crawling or asset loading.
  Strict status/header/framing/UTF-8/HTML checks fail closed. One balanced Material
  article yields inert text; scripts/navigation/active/hidden content are excluded.
- Limits: 512,000 raw HTML bytes, 128,000 UTF-8 text bytes, 32,768 header bytes,
  3-second socket timeout and a 12-second total child deadline including DNS/TLS/
  parsing. The parent kills/reaps on timeout; the child also owns a default-
  terminating POSIX wall alarm if its parent disappears. CPU (5 seconds), memory
  (256 MiB), output/file descriptor/core limits and a stripped environment bound
  the trusted parser. Only one physical fetch per API process is admitted.
- A committed 45-second token lease precedes I/O, without holding DB locks. The
  immutable copy contains canonical URL, server retrieval time, unknown version,
  complete text hash, lossless stable hashed excerpts and raw HTML hash/byte count;
  raw HTML is not retained. Snapshot and completion commit atomically with a final
  wall-clock check after writes. Changed policy requires current explicit approval.
- Successful replay/new receipts retain the same snapshot without refreshing;
  failed commands replay their original fixed error. An intentional retry needs
  a new key. Active duplicates conflict; expired receipts are sealed before replay
  returns. Membership/archive/context/source/document/project loss discards late
  output. Reprocessing preserves saved evidence. Logs omit URLs, bodies and keys.

Final validation on the completed code:

- **1,024 backend unit/API tests passed**, including **121 fetcher cases**. Synthetic
  socket/DNS/TLS/HTML fixtures cover private/mixed DNS, verified SNI/numeric pinning,
  redirect/encoding/size/header/chunk errors, parser exclusions, duplicate child
  JSON and output identity. Actual subprocesses are killed/reaped while DNS/TLS/
  slow headers/body stall; a separate test proves the child's own alarm terminates
  before a longer parent deadline. No Internet lesson, model or paid service call.
- **57 new isolated PostgreSQL/API cases passed** (39 repository, 18 HTTP): approval
  opt-in/consent, cross-tenant/project/member/original-actor rules, stale policy,
  detached hash/version validation, Unicode excerpt splitting, concurrent admission,
  durable failure/success replay, explicit retry, expired receipt/late original
  response, unlocked I/O cancellation races, source/context/project cascade cleanup,
  safe logs, authentication/no-store, strict/duplicate/oversized JSON and memory 503.
  Context-before-approval locking is tested against direct source deletion. A
  trigger expiring the lease after snapshot INSERT proves the whole write rolls back.
- **62 existing PostgreSQL/RAG/context/draft regressions passed**, including populated
  upgrade cutoffs through 0025, migration checksums and prior provenance/replay/
  deletion behavior. No frontend change or local Docker image build was needed.
- `git diff --check` passed; the public README remains product-focused.

The first test attempt exposed a test-environment issue: parallel independent
schemas installed pgvector into a temporary schema, whose cascade cleanup removed
it for the other process. Both suites were rerun serially after installing the
extension in the disposable database's public schema. Test-only timeout spelling
and a run overlapping the consent-column edit were corrected before the final
57/62-case results; none of those incomplete runs is counted as acceptance.

Validation used a separate temporary Python environment, authored in-memory
artifacts and one cached tmpfs-backed PostgreSQL container on a random loopback
port. All test schemas ended absent and that container was removed. Owner container
IDs/states, image IDs and volume names matched the before/after inventory exactly;
existing services stayed stopped. No image/model download/build, owner `.env`,
credentials, data, Docker setting or real-source deletion was involved.

Limits: this is a backend boundary, not a complete learner-facing feature. No live
page compatibility/availability, approved-document draft binding, external-topic
runtime, user generation/activation or native model-quality approval is claimed.
The strict fixed-page parser may need a reviewed update if that official page
changes. Linux resource/signal support is required.

## Step 5b — learner selection and approved-document workspace (2026-11-11)

Clean `main` at `c237b1ee45dd7e5cf21f0d7c207bae568b9e684d` matched origin before
implementation. Its [CI run 43063655617](https://github.com/emredemirbas/multimodal-rag/actions/runs/43063655617)
was still running initially, then finished with frontend/backend unit success,
backend integration failure and images skipped. The integration result was
731 passed, 10 skipped and one failure: the older visual-checkpoint migration
inventory test expected versions only through 0024. Appended 0025 to that explicit
expectation without weakening old-content/citation/checksum preservation checks.
The failed test and populated upgrade/RAG regressions now pass locally (11 cases).
This correction does not change product code or any applied migration.

Implemented the already planned learner workflow:

- Project navigation opens `/projects/{id}/learning`. Published nonempty text
  sources expose their actual `active_generation` and processing version, including
  textual video evidence; unfinished job generations are not used. Learners select
  1–20 sources and explicit experience, difficulty, language and effort. External
  topic/document preferences start unchecked. A saved context's bookmarked URL
  restores its immutable choices without adding context listing or browser storage.
- Server-only BFF routes cover context create/read/delete and catalog/document
  approval/list/read/capture/delete. They authorize the authoritative tenant/project,
  reject malformed IDs, cap JSON at 16 KiB with a read deadline and reject duplicate
  decoded keys, non-finite values, extra/server fields and cross-origin writes.
  Private/no-store/nosniff/CORP responses return fixed safe errors. Ordinary eight-
  second upstream timeouts remain; capture alone uses a bounded 25-second window.
  DELETE requires a real 204 rather than accepting a JSON-null success.
- Context receipts validate preferences, source pins and copied evidence scope, then
  expose only the lean source/preferences projection. Catalog policies and retained
  document/text/excerpt hashes are checked before browser delivery. Approval replay
  accepts the original pinned policy even if the current catalog changed; completed
  capture replay must preserve its prior snapshot and raw provenance exactly.
- Per-page selection and unchecked retrieve-and-retain consent save approval only.
  Separate capture, status-read, explicit retry and deletion controls preserve that
  distinction. Unknown version, canonical URL, retrieval date, full MIT notice,
  attribution, stable excerpt anchors and hashes are inspectable. Text is rendered
  literally through React, without HTML interpretation or automatic asset loads.
- An uncertain context body/key remains frozen if the source inventory advances or
  removes its source. Uncertain approval also retains its original policy/body/key
  across catalog refreshes; explicit form edits start a different request. Known
  capture failures require an intentional new attempt, while uncertain delivery
  replays the same command. No capture runs on mount, refresh, status read or opt-in.
- Keyed scope components, abort cleanup, context epochs, per-document revisions and
  removal tombstones fence late responses. Context/source/project disappearance
  clears cached material. Confirming deletion hides retained text immediately;
  uncertain deletes reconcile with GET before restoring any copy. Archive blocks
  new work while reads/deletion remain available. A capture POST 404 alone does
  not prove deletion: another member may read an approval but cannot capture it.
  Explicit GET status confirms actual absence without hiding a readable copy.

Final validation:

- **356 frontend tests passed** (50 files), including 30 new contract/BFF cases,
  27 new component cases, five page cases, two timeout/deletion-transport cases and
  one published-version parser case. Tests cover scope/receipt/hash tampering,
  malformed/duplicate JSON and origins, explicit opt-in/no automatic capture,
  immutable/uncertain request replay, expiry/failure recovery, deletion/scope races,
  stale lists, source-generation changes and StrictMode cleanup.
- **Lint, typecheck, lint compatibility and local production build passed** with
  installed dependencies. No new package, backend product change, migration or
  local Docker image build/download was needed for the UI.
- **11 isolated PostgreSQL migration/RAG tests passed** after the CI inventory fix,
  including the exact failing test. One existing Starlette/httpx deprecation
  warning remains; no runtime failure was suppressed.
- Browser walkthrough used a dedicated loopback Next server and authored in-memory
  API fixture. Source/preferences -> saved URL -> page selection/explicit consent
  -> approval -> separate capture -> literal text/provenance -> refresh and bookmark
  reload all worked. Fixture instrumentation recorded zero captures before the
  button and exactly one afterward; refresh/reload added none. Synthetic `<script>`
  text stayed literal. This is a UI boundary check, not live document/model quality
  or a full real-stack acceptance claim. Screenshot retained locally outside Git.
- Synthetic server-only bearer tokens were absent from production browser JavaScript.
  `git diff --check` passed and changed Markdown links resolve.

The fixture and Next servers were stopped and temporary files cleaned. Migration
checks used a cached tmpfs PostgreSQL container with its own loopback port; it was
removed after tests. Owner container IDs/states, image IDs and volume names matched
before/after. Owner `.env`, credentials, services and real data were unchanged;
no model, paid API or live official page was contacted. Next's automatically
created development instruction file was removed; generated type declarations
returned to their tracked production form.

The README adds only the actual product capability. Internal delivery/test/CI
records stay in docs. Assignment generation, document-backed drafts and activation
remain unavailable; no native-model or independent real-video quality gate closes.

## Step 5c — captured documents in immutable draft revisions (2026-11-11)

Clean `main` at `5a4db8c4a7d240a6e9ec1328a5c7c63437793aed` matched origin before
implementation and was fetched/checked again before commit. Its
[CI run 43066621806](https://github.com/emredemirbas/multimodal-rag/actions/runs/43066621806)
completed successfully in all four jobs: frontend, backend-tests,
backend-integration and images. The preceding failed run had the stale 0025
migration inventory described above. The notification image alone does not
identify its run; the exact current baseline is verified separately. This slice
needs its own hosted result.

Implemented the already planned trusted draft-document boundary:

- Existing draft create/replace accepts optional `documentation_ids` (empty by
  default, at most 20 unique IDs, canonical order). Each revision returns its saved
  selection. Nonempty selections participate in command identity; historical
  omitted/empty hashes and populated pre-0026 upgrades remain compatible.
- Only explicitly selected captured documents from the same immutable saved
  context/tenant/project can bind. Retained consent/policy fingerprint, current
  application-owned catalog ID/URL permission, aware approval/retrieval times,
  full text/excerpt hashes, lossless chunk recipe, stable UUID5s and raw hash/size
  bounds are checked. Retained metadata survives catalog metadata changes that
  preserve its allowed ID/URL. Binding never fetches or invokes inference.
- Requirements retain tutorial/prerequisite/extension labels and explicit learner
  permissions. Only cited excerpt projections are returned with original stable
  provenance; the full approval's license/attribution remains readable separately.
  A URL or client-supplied provenance cannot create evidence. Structural binding
  does not certify semantic support or assignment quality.
- Migration 0026 records every selected document as an immutable revision
  dependency, including unused selections. Approval or snapshot deletion removes
  the complete logical draft, all revisions/command receipts and its generated
  result pointer if any revision selected it. Dropping that document in a newer
  revision does not retain old copied material; unrelated drafts remain.
  Source/context/project cascades preserve complete deletion. Learner document and
  context deletion confirmations explain the draft/history effect.
- Context and sorted document fences precede draft locks. A final locked head
  check handles deletion of an older document while replacement drops it, without
  an orphan FK write or deadlock. Independent review found this race before final
  validation; both winning transaction orders are now tested.

Final validation:

- **1,024 backend non-integration tests passed.**
- **58 new isolated PostgreSQL/API tests passed**, covering canonical selection,
  authoritative excerpt provenance, policy/hash tampering, missing/pending/foreign
  documents, scoped authorization, archive/replay/history, unchanged empty hashes,
  atomic failure, logs without content, direct approval/snapshot deletion, historical
  and unused dependencies, and real synthetic publication/result cleanup.
  Concurrent create/read/replace/delete and both drop-last-document race orders pass.
- **182 existing PostgreSQL regressions passed** across migrations, visual-checkpoint
  upgrade, contexts/drafts, document APIs, delivery/execution and workflow. The first
  run passed 179 and failed three concurrency fixtures whose monkeypatched helper
  still accepted four arguments after `_bind` gained an optional fifth argument.
  Updating only those helper signatures and rerunning all three passed; assertions
  and lock/deletion expectations were preserved. All explicit migration inventories
  now include 0026, avoiding the earlier CI inventory omission.
- **19 saved-context frontend tests and lint passed**, including the existing
  document-delete race test's assertion that confirmation mentions revision history.
  No frontend runtime/type dependency or product README change was required.
- Independent code/document review found no remaining blocker. `git diff --check`
  and changed Markdown link checks passed before commit.

Validation used synthetic in-memory document text, a separate temporary Python
environment and one cached tmpfs-backed PostgreSQL container with its own random
loopback port. Remaining test schemas were zero; the owned container was removed.
Owner container IDs/states, image IDs and volume names matched the before/after
inventory exactly. No local image build/download, model, paid API, live lesson
fetch, owner `.env`/credentials/service change or real-data deletion was involved.

Limits: this is the draft API boundary, not the learner draft editor or an enabled
generator. No native model quality, independent real-video quality, activation,
submission or grading gate closes. The graph still rejects all true external flags.

## Continuation

Continue planned Step 6 **within Sprint 5** with bounded draft discovery/read/edit
UI. First inspect discovery support and add only the scoped query needed to reach
saved drafts. Reuse existing versioned APIs and explicit document selection;
preserve evidence labels, revision conflicts, uncertain-command replay and deletion
fences. Activation remains a separate planned slice. Do not generate content just
to populate the UI, or treat this as starting Sprint 6 submissions/grading.
Keep the empty default registry/public generation closed: native latency, literal
quotes, core-skill/semantic abstention and full generated-draft review remain open.
No new prompt retry loop, relaxed checks, paid calls/downloads, grading/tutoring or
Alpha 2 closure follows. Verify this new commit's exact hosted CI; running is not
success and a prior passing commit does not prove this slice's hosted result.
