# Sprint 5 — learning objectives and assignment drafts

Date: 2026-10-29. Status: explicitly authorized by the owner; first internal
contract/evidence slice implemented and locally tested. This is the next selected scope after the
accepted RAG milestone, not an automatic sprint transition. The independent
real-video quality/audiovisual gate for full Sprint 4/Alpha 2 stays open.

## Outcome and boundary

A learner selects published project sources and learning preferences, inspects a
versioned coverage map, requests a local-model coding exercise, edits its cited
requirements and explicitly activates a version. Every requirement is labelled
`covered`, `prerequisite` or `extension`; external material has separate official
documentation provenance. Unsupported coverage must be reported, not invented.

Keep FastAPI/Pydantic, PostgreSQL, Celery/outbox and application-owned providers.
No paid endpoint, automatic model download or incidental owner-stack change.
Submissions, code execution/grading, runtime progressive tutoring, deadlines,
reminders and mastery remain later-sprint work. Acceptance criteria/rubrics/hint
content in a draft are descriptive data, not executable checks or grading results.

README remains public product documentation: capabilities, setup, usage,
architecture, constraints and development links. Sprint plans, milestones,
validation counts, CI run identities and handoff instructions belong in `docs/`.

## Product decisions and surfaced assumptions

- Explicit source selection supports one tutorial or a selected set of linked
  playlist lessons. No empty selection meaning “all future sources”; pin exact
  successful generations and processing versions at acceptance. Reprocessing
  must not silently broaden or replace that selection.
- Difficulty, language, available effort and external-topic permissions are
  explicit request fields initially. Do not silently confirm the old proposed
  2–4 hour default. Initial language choices are English/Turkish, consistent with
  current local use; language must be selected rather than inferred from metadata.
- Owner answer pending: tutorial-only forever, or tutorial-only by default with
  optional prerequisite/extension material. The first contracts carry explicit
  permissions; no runtime choice is enabled before this decision is recorded.
- Owner answer pending: opt-in automatic official-document retrieval from an
  application allowlist, or document selection/approval before each retrieval.
  The first slice contains no fetcher or approved-domain default. Its binding
  interface accepts only already-authorized trusted documentation snapshots.
- Draft updates use optimistic version checks. Activation produces a pinned
  version; corrections can start a new editable draft, preserving the old version.
  This satisfies ADR 0010's eventual post-submission immutability without adding
  submission behavior now. Final activation/version API is implemented in step 6.
- Deleting a source must remove derived objective/draft/version text that depends
  on it, not merely delete citation rows. Complete project deletion removes all
  curriculum snapshots, checkpoints and model-call attribution as applicable.
  This follows the existing derived-answer deletion rule; no deletion exemption.

## Ordered implementation slices

### 1. Strict domain contracts and authoritative evidence binding — implemented

Files: `backend/app/curriculum/contracts.py`, `validation.py` and focused tests.

Define explicit scoped requests, learner preferences, source-version pins,
objective/evidence data underlying coverage, requirements, acceptance criteria, qualitative rubrics,
ordered hint content and a bounded draft. Reject unknown fields, empty text,
coerced booleans/numbers, duplicate identities and dangling cross-references.
Bound payload/list sizes; report overflow instead of silently truncating coverage.

The model supplies evidence IDs only. Resolve IDs from authoritative, same-tenant/
project, selected-source snapshots using the existing `EvidenceView` and ASR/visual
provenance types. Application code supplies timestamps, source labels, immutable
segment identity, processing version and generation. Keep old retained generations
valid; reject mismatched source/version pins and missing/duplicate/foreign IDs.

Separate tutorial evidence from approved documentation snapshots. Covered
objectives/requirements need tutorial evidence; external requirements need their
separate document evidence and explicit permission. Structural binding establishes
identity and scope, not that a claim is semantically supported or an exercise is
solvable. Preserve machine-generated/unreviewed provenance without promoting it.

This slice is internal and pure: no API, durable record, migration, model call,
worker or UI is claimed delivered. Safe error codes contain no source/model text.
Later repository code must still authorize membership and fence deletion races;
passing a scoped DTO is not authentication.

### 2. Project-owned persistence and read/edit API

Add the next migration (currently 0020) and `curriculum/repository.py`.
Persist project-scoped learner settings, immutable source/evidence/coverage
snapshots and versioned editable drafts with tenant/project composite keys.
Use project/membership locks, archived-project write fences, idempotent request
replay/conflict detection and optimistic edit revisions. Revalidate dependencies
in the commit transaction. Add source/project deletion behavior from this first
persisted slice, including derived text and private staging.

Expose only completed persisted data. API authentication/isolation and no-store
contracts precede frontend wiring. Reuse existing evidence inspection rather than
creating a second citation format. Database integration tests cover migration
upgrade/repeat, foreign scopes, concurrent edits/replay, archive and deletion.

### 3. Durable curriculum runs and attribution

Existing `processing_jobs`, `outbox_events` and `usage_events` are source-owned;
assignments can span sources. Do not invent a synthetic source or advance source
index generations to host assignment work. Add dedicated project-owned run,
attempt/outbox/checkpoint and per-model-call attribution tables with migrations.

Reuse Celery delivery, scheduler, scoped lease and orphan/retry patterns in a
separate curriculum queue/worker. Accept source pins before inference; one bounded
stage per delivery, no provider call under a database lock. Commit/checkpoint after
checking the original actor, membership, live lease, cancellation and dependencies.
Store each accepted stage once, including failed/revised call metadata and actual
usage. Unknown tokens stay null; billed service spend is zero. Logs/metrics expose
IDs/stages/codes/counts/timing, never tutorial/model text or credentials.

Retry reuses committed outputs; an interrupted uncommitted call may repeat.
Test actual worker loss/redelivery, retries, revoked access, cancellation and
source/project deletion using isolated schemas/queues/objects/processes.

### 4. Local provider and model-driven LangGraph workflow

Add an application-owned assignment provider, separate from chat's answer schema
and short context limits. Reuse local-only URL/transport rules; no proxy, redirect,
cloud fallback or automatic weight installation. Missing/busy/unavailable models
produce honest capability/failure states. Fixtures are labelled synthetic and do
not masquerade as real generation in the product.

Pin model digest/engine and prompt/schema/graph/context versions. Process bounded
source batches into objectives and a coverage snapshot; make omitted/unsupported
coverage inspectable. Run a finite graph: generate -> deterministic contract and
binding validation -> optional bounded model revision -> validate -> draft or
explicit failure. The model cannot waive deterministic invalidity. No arbitrary
tools or code execution. A revision limit is explicit, not an open-ended loop.

Graph state is subordinate to the scoped durable run. Persist accepted node results
under the application lease/deletion fence; do not introduce an unscoped library
checkpoint store. LangGraph is added/pinned only in this slice and orchestrates
model-driven transitions, never CRUD or the queue. Node replay/idempotency and
accepted-output reuse need failure tests; a checkpoint does not make side effects
exactly once. See the [official workflow guide](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
and [graph replay guidance](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx).

### 5. Official documentation snapshots

Implement the owner's chosen retrieval policy before enabling external topics.
Maintain an application-owned exact-domain/route allowlist; no arbitrary supplied
URL fetch, off-allowlist redirect, credentials or model-selected destination.
Bound time/bytes/content type, persist canonical URL, retrieval time, detected
version (explicitly unknown if unavailable), content hash and stable excerpt IDs.
Validate links and record the approved source/license policy separately from
model output. All stored project copies and derived text follow project deletion.

Covered/prerequisite/extension labels and tutorial-versus-document citations remain
separate. A documentation URL alone does not prove the tutorial covered a topic.
Test SSRF/redirect/oversize/stale-version cases with local HTTP fixtures, no paid
or unapproved live fetches. UI must make any required document approval explicit.

### 6. Learner workspace, draft review and activation

Add source selection and explicit learner preferences, coverage inspection,
generation progress/cancel/retry, draft editing, validation errors and requirement
labels with stable tutorial/document links. Provide loading/empty/error/success
states, keyboard navigation and visible status announcements.

Require explicit activation of the reviewed valid revision; replay is idempotent.
Changing selected sources/preferences creates a new context/draft rather than
rewriting active provenance. Keep job recovery separate from an uncertain browser
response. Test BFF receipt/scope binding, stale edits/deletion races, saved draft
recovery and old published evidence after reindexing. Add no submission UI or code
runner and no runtime deadline/tutor workflow in this step.

### 7. Finite Sprint 5 acceptance

Use existing unit/API/PostgreSQL/worker/UI techniques and a disposable default/
opted-in local stack, not a new evaluation service. Verify selected-source ->
coverage -> generated draft -> edit -> activate -> inspect evidence, plus
unsupported input, cancellation/retry/recovery, isolation and complete deletion.

Before observing model outputs, record a small owned/licensed sample and expected
supported objectives, forbidden extensions and insufficient-evidence cases. Review
actual locally generated drafts for honest coverage, feasible effort, consistent
requirements and useful acceptance criteria. Software/schema tests do not replace
that review. Record results and known failures; do not infer representative model
quality or close the outstanding real-video review from this exercise.

Done means these scoped flows and their required review pass, with migrations,
authorization, recovery, attribution and accessible UI recorded. Do not extend the
sprint with extra evaluators/features or begin submissions/grading automatically.

## Current continuation point

Step 1 is implemented: strict contracts and authoritative evidence binding,
78 focused tests (also passing on Pydantic 2.10.0) and 713 backend non-integration
tests passed. Actual results and limits are in `validation-record.md`. README now
contains product guidance; operator details are in `../local-development.md`.
Next is step 2's scoped persistence/API design and migration, while resolving any
still-pending product policy before dependent generation/fetch behavior. Check
the exact pushed commit's CI; no generated-assignment UI/workflow is claimed yet.
