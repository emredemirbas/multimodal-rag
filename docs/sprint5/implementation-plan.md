# Sprint 5 — learning objectives and assignment drafts

Date: 2026-10-29. Status: explicitly authorized by the owner; internal contracts,
saved contexts/versioned editable drafts, durable runs and separate queued
delivery/atomic publication, local provider and internal bounded LangGraph
workflow implemented. Native-output review and public enablement remain open.
This is the next selected scope after the
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
- Owner confirmed 2026-10-29: tutorial-only by default, with prerequisite/extension
  material available only after explicit learner opt-in. Keep requirement labels
  and tutorial/document evidence separate. The current internal path still rejects
  true flags until approved documentation capture is implemented.
- Owner confirmed 2026-10-29: learner selection/approval for each official document
  before retrieval; external-topic opt-in does not authorize automatic fetching.
  Keep the application allowlist as an additional restriction. The current binding
  interface accepts only already-authorized trusted documentation snapshots;
  no fetcher or approved-domain default is enabled yet.
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

**2a — implemented:** migration 0020, `curriculum/persistence.py`, `repository.py`
and `http.py`. Save explicit preferences and exact selected source generations
with their authoritative evidence in an immutable context. There is no global
learner default and no generated objectives/coverage claim. The API accepts only
source pins and preferences, never client-supplied evidence or scope metadata.

`POST /api/v1/projects/{project_id}/curriculum/contexts` accepts this shape;
example values are caller choices, not application defaults:

```json
{
  "idempotency_key": "save-learning-context-001",
  "selected_sources": [{
    "source_id": "00000000-0000-0000-0000-000000000001",
    "generation": 1,
    "processing_version": "transcript-chunks-v1:g1"
  }],
  "learner": {
    "experience": "intermediate",
    "difficulty": "beginner",
    "language": "tr",
    "available_minutes": 90,
    "allow_prerequisites": false,
    "allow_extensions": false,
    "allow_external_documentation": false
  }
}
```

Use real published IDs/parser values from the selected project. Same key/input
replays the same 201 response; changing input returns 409. Source order is
canonicalized. `GET` and `DELETE` on the returned context ID read/remove it;
successful delete returns 204, missing context returns 404. Archived projects
permit read/replay/delete, but block a new capture. Contexts are immutable; there
is no context-list or activation API in this slice.

Recheck and lock membership after identity mapping, then lock the project and
selected sources. Load/validate/copy evidence in the same transaction. Retained
old generations and legacy published generation-one transcripts remain valid.
Exact existing ASR/visual origins and labels are copied, with no fabricated scores.
Source reprocessing cannot rewrite an existing context; deletion of any source
removes the entire multi-source context, including copied text and replay state.
Project deletion cascades all new rows. No new object-storage artifact is created.
The existing identity bootstrap still provisions membership on a later authenticated
request; these repository locks do not claim persistent local-identity revocation.

The authenticated JSON body is bounded to 16,384 actual bytes before parsing,
including chunked input. Reject duplicate keys/nonstandard JSON constants and
unknown fields. All responses, including errors, are private/no-store. Capture
all segments of the selected generations or fail without truncation: <=500 total
segments/500,000 characters, existing per-segment bounds, <=4,000,000 serialized
snapshot bytes. This is not a prompt budget or an assertion of semantic coverage.
Stored permissions enable no model or documentation access in this slice.

**2b — implemented:** migration 0021 and `curriculum/drafts.py`. Draft headers
refer to immutable contexts; append-only content revisions contain objectives,
labelled requirements, stable evidence references, acceptance/rubric links and
ordered hint content. These are versioned objective/coverage inputs, not a new
semantic coverage score or a claim that all tutorial topics have been extracted.
No separate coverage CRUD/schema is necessary before model extraction in step 4.

`AssignmentContent` is the shared unscoped content schema; `AssignmentDraft`
adds server-owned scope for deterministic binding. HTTP accepts JSON UUID text
explicitly while preserving strict numbers, unknown-field rejection and the
existing draft validation. Only cited evidence from the saved context is returned;
clients cannot supply timestamps, source labels, scope or trusted documentation.

Draft endpoints under `/api/v1/projects/{project_id}/curriculum`:

- `POST /contexts/{context_id}/drafts`: `{idempotency_key, content}` creates
  revision 1 and returns 201.
- `GET /drafts/{draft_id}` reads the latest revision; `GET
  /drafts/{draft_id}/revisions/{revision}` reads that exact saved revision.
- `PUT /drafts/{draft_id}`: `{idempotency_key, expected_revision, content}` fully
  replaces the content by appending a revision. A stale expected revision returns
  `draft_revision_conflict`/409 without reserving the new key or changing data.
- `DELETE /drafts/{draft_id}` removes all its revisions/receipts and returns 204.

`content` is the existing `assignment-draft-v1` shape without tenant/project
fields. Revision responses include draft/context IDs, accepted revision/time and
a scoped bound assignment. They do not include a dynamic current-head value.
Project-scoped command keys bind operation, target, expected revision and content;
an identical retry returns its original immutable revision even after newer edits
or archive. Reusing the key for different input/operation/target returns 409.
Archive permits history/replay/delete but blocks new create/edit operations.
An accepted replacement with identical content and a new key is a new revision.

Reauthorize/lock membership and project, then hold the context row as the
dependency deletion fence. Do not acquire source row locks after the context:
direct source deletion takes the opposite order via its cleanup trigger. Rebind
every new revision against the saved context within the transaction. Append the
revision, receipt and head update atomically. Source/context/project deletion
cascades all draft/objective text and replay state, including unused selected
source dependencies. Reprocessing cannot replace pinned evidence.

Draft mutation bodies allow <=272,384 actual wire bytes; the context limit stays
16,384. The scoped normalized draft remains <=256,000 UTF-8 bytes, with a separate
300,000-byte spaced JSONB storage bound. Reject actual NUL text before PostgreSQL;
literal escape text remains ordinary content. Invalid input/storage overflow
leaves no partial draft/revision/receipt. Responses stay private/no-store and logs
contain IDs/revisions/counts, not content or request keys.

Only client-supplied draft content is persisted here. Structural binding is not
semantic support, feasibility, quality approval, activation or deterministic code
assessment. No generation/docs provider is called. External/document requirements
cannot be bound without trusted snapshots that step 5 has not delivered; saved
permission flags alone do not authorize document fetching or enable this capability.

Database/API tests cover migration upgrade/repeat, foreign scopes, concurrent
replay, archive, retained generations, managed provenance, resource overflow,
source deletion and actual membership/source lock waits. Frontend wiring remains
later; no generated-assignment UI or qualitative approval is implied.

### 3. Durable curriculum runs and attribution

Existing `processing_jobs`, `outbox_events` and `usage_events` are source-owned;
assignments can span sources. Do not invent a synthetic source or advance source
index generations to host assignment work.

**3a — implemented:** migration 0022 adds dedicated project/context-owned
`curriculum_runs`, `curriculum_run_attempts`, `curriculum_run_outbox`,
`curriculum_run_commands`, `curriculum_run_checkpoints` and
`curriculum_model_calls`. Internal `RunRepository` and `RunProgressRepository`
provide the scoped lifecycle and progress boundary. Step 3b below adds delivery
and success/publication; no HTTP producer or model invocation is enabled.

Creation pins an existing immutable context and an explicit application workflow
version. It atomically writes a pending run and its own outbox row; create replay
does not enqueue another run. Pending/running/retrying/failed/cancelled and, with
0023, succeeded are the implemented states. One claim wins per run, with a fresh token and monotonically
increasing attempt number. Three automatic failures end in failure; a new explicit
retry command from the original actor resets that budget while preserving accepted
checkpoints. Cancel invalidates the current lease immediately. Cancel/retry keys
replay their immutable accepted state even after a later retry/state change.

Worker fences derive original actor/context from the stored run, never from a
delivery. Lock membership -> project -> context -> run; never source after context.
Use `clock_timestamp()` after lock waits, a 180-second lease and a five-second
automatic retry delay. An expired heartbeat cannot renew its lease. Scoped recovery
closes a lost attempt once; archive/revoked original membership terminally block
work rather than leave a running orphan. Stale tokens/attempts and deleted context
cannot read or save progress. These are internal safety constants, not learner
time/difficulty defaults. Existing identity bootstrap policy remains unchanged.

Private checkpoints have sequential immutable identities, workflow/stage identity,
an accepted attempt and a content hash. Exact replay succeeds; changed content or
out-of-order appends conflict. Bound payloads to 64 checkpoints, 300,000 compact
UTF-8 bytes each and 327,680 actual JSONB bytes. Normalize JSONB numeric values
before hashing/storing so exponent/negative-zero load/replay remains stable; reject
exponent expansion, NUL and non-finite values safely without partial writes.
Generic private graph state is not validated tutorial coverage or a published draft.

Declare each local physical call before invocation with its UUID, purpose,
model/digest/engine/prompt version and input counts. The start fingerprint identifies
that metadata, not raw prompt bytes. Finish records actual duration/character/token
counts; unknown counts remain null and actual zero remains zero. Accepted completion
receipts cannot be edited. A cancelled/lost/failed attempt interrupts started calls
without inventing usage or duration. A physical retry needs a new call ID; limit
call records to 256 per run. This slice records synthetic call lifecycle in tests
and invokes no model. There is no model selection/download default.

Source/context/project deletion cascades all six tables, including private payloads,
receipts and attribution for unused selected dependencies. Outbox state changes
are atomic with lifecycle transitions. Logs contain scoped IDs/status/counts or
stages, never checkpoint text, model payload, credentials or request keys.

**3b — implemented:** migration 0023, `RunDeliveryRepository`, private stage
contracts and a separate `curriculum.advance_run` Celery task/queue. The existing
scheduler delivers its own outbox, retries publication failures, rearms sent but
unclaimed work after 60 seconds and recovers expired run leases in bounded batches.
Broker calls hold no database locks. All acknowledgements include the outbox lease
token, so a fast continuation cannot be hidden by the previous publish ACK.

The optional `curriculum-internal` Compose worker profile has one process slot,
90/120-second soft/hard task limits below the 180-second run lease, fixed resource
bounds and no model/object-store service dependency or shared object credentials.
Default startup stays unchanged. Its app-owned processor registry is empty:
unknown workflow versions fail terminally with `processing_unavailable`. No
environment-selected imports or runtime fixture generator exist. Public run
creation/generation stays closed until the real processor exists in step 4.

Each delivery loads detached authorized input and accepted checkpoints, releases
DB locks and executes at most one trusted stage. The private stage input includes
a detached claim for before-invocation call attribution. A stage returns either
one new sequential checkpoint or strict final content. Checkpoint acceptance,
attempt closure (`checkpointed`), pending state and outbox reset commit together.
The next delivery gets a fresh token/attempt; accepted continuation does not spend
a failure, and an already accepted sequence cannot yield indefinitely.

Final content is rebound against the immutable context in the live transaction.
New draft/revision, exact revision result, attempt/run success and outbox removal
commit together. Both output paths recheck wall time after their last outbox write;
expiry rolls the entire transaction back. Neither path can leave started model
calls orphaned. The result relation survives later draft edits as the original
revision pointer. Deleting a draft removes its result pointer while its succeeded
run stays terminal; stale deliveries cannot restore it. Dependency deletion
continues to remove every copied private/result row. No user command key is forged
for generated publication.

Real Redis/Celery SIGKILL tests cover loss before final output commit and after
checkpoint commit/before acknowledgement, plus duplicate delivery and one-result
publication. Synthetic stage adapters live only in test subprocess code. The
database/worker tests establish delivery recovery, not actual model generation,
semantic support, tutorial coverage or exercise solvability.

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

Implement this step in two bounded slices. **4a (implemented):** a separate local JSON
provider and fenced physical-call attribution, with an explicit model/engine pin,
request fingerprint and transport/resource bounds. Validate it with authored HTTP
responses and isolated PostgreSQL; do not call the owner's model or register a
generation processor in this slice. **4b (implemented internally):** application
prompts, objective/coverage batching and finite LangGraph transitions/checkpoint
continuation. Native supported-draft quality still needs review. The owner has
confirmed optional external topics with per-document approval; dependent approved
capture/enablement remains unimplemented.

`LocalCurriculumProvider` implements the application-owned JSON interface;
`LeasedCurriculumCalls` connects it to the existing scoped call ledger. Migration
0024 adds exact serialized request-body hash and schema/request versions. Old
metadata-only rows remain null and preserve their original replay fingerprints.
Start/finish writes recheck wall time after the write; expired receipts roll back.
Returned JSON receives application-contract/evidence validation in 4b;
the adapter does not claim semantic support or generate a published assignment.
The default worker registry and public capability remain closed.

4b implementation boundary: internal tutorial-only workflow for explicit false
prerequisite/extension/documentation permissions. Other permissions fail before
inference until approved document capture exists; this does not forbid the owner's
confirmed opt-in behavior permanently. Default processor registration/public generation stays
closed. Pin LangGraph 1.2.18 (Python >=3.10), disable hosted tracing explicitly
without changing owner environment variables, and use no library checkpointer.

Split source text losslessly at Unicode character boundaries into <=1,800-byte
prompt slices, preserving original evidence IDs and exact character offsets.
At most four slices/batch and 20 batches; refuse larger contexts before inference,
without truncating or silently selecting sources. Extraction returns <=2 goals
per batch with exact quotes and a model-reported supported/insufficient status for
every slice. These are unreviewed interpretations, not semantic quality scores.
Select <=4 of the <=40 extracted goals for a small draft; retain unselected goals
as explicit omissions from that assignment. Bounds are technical limits, not
hidden learner effort/difficulty defaults.

One delivery initializes/pins state without inference; later deliveries make at
most one physical call each (extract, select, generate or revise), followed by
deterministic validation and an atomic checkpoint or bound draft publication.
Accepted extraction/selection checkpoints are reused after process loss. Invalid
extraction/selection fails safely; an invalid draft receives at most one revision
with bounded raw proposal and fixed feedback codes. Oversized repair input fails
without truncation. At most 23 checkpoints/23 physical workflow calls, excluding
the existing explicitly bounded transient retry budget. No model may waive schema,
scope, selected-objective, evidence, effort or covered-only requirements.

The transport follows the official [Ollama chat API](https://docs.ollama.com/api/chat)
and [structured-output guide](https://docs.ollama.com/capabilities/structured-outputs).
Local inventory found pre-existing `qwen3:4b` on Ollama 0.40.3; the exact observed
digest is in the validation record. This is not a hardcoded digest default or
permission to replace/install weights.

4a technical bounds: existing approved `qwen3:4b` only; explicit full digest and
engine identity, no automatic model selection/install/fallback. At most 12,000
combined UTF-8 message bytes, 16,000 schema bytes, 65,536 request bytes, 262,144
response bytes and 128,000 output-content bytes. These byte bounds are not token
estimates or whole-context coverage claims. Fixed decoding uses a 16,384 context,
2,048 output tokens and four CPU threads. A 60-second acceptance deadline covers
preflight/inference/postflight; socket timeouts are at most 2 seconds for metadata
and 42 seconds for inference. Reject late output; the worker's 90/120-second
soft/hard limits remain the ultimate process boundary for blocked I/O. No hidden
learner effort/difficulty default is introduced by these resource constants.

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
checkpoint store. LangGraph is added/pinned only in 4b and orchestrates
model-driven transitions, never CRUD or the queue. Node replay/idempotency and
accepted-output reuse need failure tests; a checkpoint does not make side effects
exactly once. See the [official workflow guide](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
and [graph replay guidance](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx).

### 5. Official documentation snapshots

Implement the owner's per-document selection/approval policy before enabling external topics.
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

Steps 1, 2a, 2b, 3a, 3b, 4a and internal 4b are implemented: contracts/binding, saved contexts,
versioned draft persistence/API, durable runs and separate queued delivery with
fenced publication, plus a pinned local JSON provider, scoped call attribution and
bounded objective/coverage extraction, selection, generation and one revision.
Results and limits are in `validation-record.md`. README
contains product guidance; operator details are in `../local-development.md`.
The small predeclared native review is recorded in `native-output-review.md`.
Supported cases exposed local latency and extraction-contract failures; a bounded
schema/prompt correction preserves strict grounding. No supported native draft
quality is claimed yet. Next address the demonstrated extraction latency/quote
binding within a finite local worker budget before enabling generation; preserve
the existing lease/call/checkpoint fences and do not increase limits blindly.
No downloads or default/public enablement. The owner confirmed tutorial-only by
default, optional external topics and approval for each official document; implement
approved capture in step 5 before their runtime behavior, then the planned draft
review/activation workspace. No user-facing generation/activation flow is claimed.
