# Sprint 5 — validation record

Date: 2026-10-29. Status: first internal contract/evidence slice implemented;
assignment persistence, model generation, review/activation UI and full Sprint 5
acceptance remain undelivered. The ordered plan is `implementation-plan.md`.

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

## Delivered internal boundary

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

This is a pure internal foundation. It does **not** authorize membership, resolve
concurrent deletion, establish semantic support/solvability or deliver generated
assignments. The next repository slice must reauthorize and revalidate dependencies
under a transaction fence with tenant/project composite keys and complete derived-
text deletion. No API, migration, persisted curriculum row, worker, model call,
new dependency, owner-data mutation or running-service change was introduced.
No assignment quality, full Sprint 5 or full Alpha 2 approval is implied.

## Continuation

Next: step 2 in `implementation-plan.md`, project-scoped learner settings,
pinned evidence/coverage snapshots and editable draft persistence/API with the
next additive migration (currently 0020). Follow existing chat authorization and
replay patterns. Do not repurpose source-owned ingestion jobs for multi-source
curriculum work; later durable runs need project ownership and per-call usage.

Resolve the pending extension and official-document policy before enabling their
dependent behavior. Preserve source-generation pins, no paid calls/downloads,
complete deletion and the separation from later submission/grading/tutoring work.
Verify the exact new commit's hosted CI after push; the green starting baseline
alone does not certify this first implementation.
