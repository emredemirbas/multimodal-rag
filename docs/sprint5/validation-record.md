# Sprint 5 — validation record

Date: 2026-10-29. Status: internal contracts and immutable saved tutorial context
persistence/API implemented. Editable assignment/coverage persistence, model
generation, review/activation UI and full Sprint 5 acceptance remain undelivered.
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

## Continuation

Next: step 2b in `implementation-plan.md`, versioned editable drafts and
coverage/objective persistence/API using the saved context, with the next additive
migration (currently 0021). Preserve authorization, optimistic edit revisions,
mutation-receipt replay and complete source/project deletion. Do not repurpose
source-owned ingestion jobs for multi-source curriculum work; later durable runs
need project ownership and per-call usage.

Resolve the pending extension and official-document policy before enabling their
dependent behavior. Preserve source-generation pins, no paid calls/downloads,
complete deletion and the separation from later submission/grading/tutoring work.
Verify the exact new commit's hosted CI after push; the green starting baseline
alone does not certify subsequent implementations.
