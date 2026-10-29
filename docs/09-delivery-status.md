# Delivery status and finish lines

Date: 2026-10-29. Current authorized work: **Sprint 5**, in staged implementation.
The owner explicitly requested this new scope after the RAG milestone.
**RAG portfolio v1 is complete** within its selected local transcript RAG scope.
Accepted application baseline: `3c2bff5`; local acceptance and all four hosted CI
jobs passed. Later documentation-only commits retain this accepted baseline.

## Where we are

**Sprint 5 has contracts, saved contexts, versioned draft APIs, durable queued delivery/publication and a local provider foundation**; full
Sprint 4/Alpha 2 quality approval remains open. Project/auth/isolation,
authorized subtitle jobs, scoped retrieval/chat/citations, optional free local
answers/embeddings, ordered playlist relationships, constrained WAV transcription
and constrained MP4 -> retained frames/OCR -> indexed frame citations exist.
Optional explicitly pinned local image-model descriptions now feed separately
labelled versioned visual evidence, with inspectable uncertainty and recovery.
Media uploads are independently opt-in; configured availability is not readiness
or quality. Original retirement/verified cleanup and complete deletion are tested.

The exact `3c2bff5f01c3a09d3932159e39c08faa513e27d0` acceptance commit was
verified on 2026-10-29: all four hosted CI jobs completed successfully in
[run 40854790466](https://github.com/emredemirbas/multimodal-rag/actions/runs/40854790466).
Frontend: 291 tests; backend unit/API: 635 tests; standalone PostgreSQL: 388 passed
and 10 skipped; full-stack real-worker integration: 398 passed with no skips.
Image/native-media, smoke, recovery and cleanup checks also passed.
Software test counts are not representative ASR/OCR/RAG quality approval. Known
mixed-language OCR/ASR vocabulary limitations remain in the validation records.

| Work | Current state |
|---|---|
| Sprints 0–2: foundation, projects, transcript ingestion | Implemented and validated within the documented local scope |
| Sprint 3: RAG/chat/evidence | Implemented local baseline plus optional local models; representative quality review remains open |
| Sprint 4: playlist and multimodal evidence | WAV/MP4/OCR, frame citations, opt-in change selection, user-asserted timeline and optional local image descriptions exist; independent real-example audiovisual/quality verification remains open |
| Sprint 5: learning objectives and assignments | Context/draft APIs, durable delivery/publication and pinned local JSON/call-attribution foundation implemented (0020–0024). Objective/coverage prompts, LangGraph generation, UI and pending policy remain; see the plan/validation |
| Sprint 6: submissions and hardened deterministic grading | Not implemented; largest technical/security uncertainty |
| Sprint 7: progressive tutoring/deadlines/mastery | Not implemented |
| Sprints 8–9: broader hardening and hosted beta | Portions of safety/observability exist already; production/beta launch is not the selected portfolio target |

## Selected portfolio v1 — finite scope and acceptance

The owner selected this first finish line on 2026-10-29. It demonstrates the
existing authorized transcript RAG flow locally, without paid APIs/services or
model downloads. It is not the completion of the longer learning-platform vision.

| Acceptance criterion | Evidence / current state |
|---|---|
| Reproducible keyless local startup, documented prerequisites and licensed sample | Fresh default Compose build/start passed on empty dedicated volumes; `/demo` and exact MIT sample/license downloads verified |
| Authorized SRT/VTT -> actual queued processing -> project/source-scoped answer or explicit abstention | Canonical downloaded VTT uploaded through the browser; real queue reached ready; both supported questions cited the expected chunk and unsupported Kubernetes question abstained |
| Inspectable source/timestamp/processing generation, saved chat and recoverable delivery/reprocessing | Browser evidence/transcript/history checks passed; all four existing smoke scripts passed, including disconnect replay and generation stability |
| Complete source/project deletion, tracked physical cleanup, isolation and accessible recovery states | Browser source removal hid both cited turns while preserving draft/limitation; history stayed clean; source/project cleanup completed; isolated DB/bucket ended empty. Isolation remains covered by verified baseline CI |
| Truthful README/demo, explicit optional-feature limits, current validation and green hosted application checks | README/demo and baseline docs agree; local checks and all four hosted jobs passed for accepted commit `3c2bff5` in run `40854790466` |

Only a defect exposed by these checks can add implementation work. Do not create
another evaluator, feature, polish backlog or new release threshold to extend v1.
All five criteria passed and their actual results are recorded. The selected
v1 milestone is complete; automatic sprint progression stops here.

Optional local answers/semantic embeddings, ordered metadata relationships,
restricted WAV/MP4, OCR, change selection, temporal inspection and image descriptions
remain available at their existing documented experimental boundaries. Their
setup/native evidence and limitations stay visible; v1 does not require enabling
all profiles or certify representative model/media quality. The MIT sample is
synthetic and has no corresponding recording.

Assignment generation, solution uploads, hardened deterministic code assessment,
progressive tutoring/deadlines/mastery and the later learning loop stay on the
original Sprint 5–7 roadmap in `04-sprint-plan.md`, **after v1**. Hosted production/
SaaS and beta operations are outside this selected target. Completing v1 does not
start any of those sprints or settle their unresolved product decisions.

## Current continuation point

The selected scope, README/demo corrections and fresh default acceptance are
recorded in `sprint4/validation-record.md` under **Portfolio v1 scope and fresh
keyless acceptance (2026-10-29)**. No new feature/evaluator/schema or model setup
was needed. The disposable stack used separate credentials, random loopback ports,
new volumes and no optional profiles. Its test project and retained files were
removed; the temporary stack/volumes were removed and existing container IDs
were unchanged.

**No remaining v1 implementation or acceptance work.** CI run `40854790466`
for the exact acceptance commit `3c2bff5` completed successfully in all four jobs.
The dated closure entry in `sprint4/validation-record.md` records the result.
This documentation-only closure does not change the accepted application code;
its own workflow status must still be reported honestly.

The owner has now explicitly selected Sprint 5 planning and staged implementation.
The current plan is `sprint5/implementation-plan.md`. Strict curriculum contracts
and authoritative evidence binding, immutable saved contexts and versioned draft
create/read/edit/delete, durable run lifecycle/progress and separate curriculum
queue/worker delivery, continuation, fenced publication and the pinned local JSON
provider/call-attribution foundation and internal bounded LangGraph workflow are
implemented. The graph extracts objectives/coverage, selects a small goal subset,
generates and allows one revision, reusing scoped checkpoints after process loss.
Native-output quality review is next, followed by policy-dependent official-document
snapshots and draft review/activation UI. Submissions and grading remain later.

The source-owned ingestion job/outbox/usage schema must not be repurposed with a
fake source for multi-source assignments. New persistent curriculum work needs
project-owned migrations and its own attribution/recovery/deletion coverage.

README now follows product-documentation style; operator detail is in
`local-development.md`, while plans, validation and CI history stay here. The
same rule is recorded in `../AGENTS.md` for future updates.

Next `devam`: read `sprint5/validation-record.md` and the current plan, verify Git/CI,
and perform the planned small native-output review of step 4b. Record an owned/
licensed sample, expected goals, forbidden extensions and insufficient-evidence
cases before calling the pre-existing explicitly pinned local model through an
isolated context/run. Inspect actual drafts/effort/hints and record failures.
Authored HTTP and real SIGKILL recovery checks establish software behavior, not
semantic coverage/solvability. Keep the default registry/public producer closed;
no downloads or owner-data/service changes. Resolve pending extension/document
policy before dependent fetch/enablement. Do not claim Sprint 5 complete or close
the independent real-video gate from these tests; do not start grading/tutoring.

## Sprint 4 closure — one remaining gate

The previous continuation added the user-visible read-only frame/transcript timeline:
explicit same-recording assertion, signed offset, actual-PTS/span matching, honest
gaps, stable evidence links and both published generations pinned in the URL.
It does not automatically verify the recording, persist a pairing or alter search.
See `sprint4/timeline-alignment.md` for API/UI behavior and validation.

Keep the remaining list finite; no more sampling/evaluator experiments are assumed
prerequisites simply because they are possible:

The image-description software gate is now implemented (ADR 0029): a default-off,
digest-pinned local vision provider, one-frame checkpointed jobs, strict structured
descriptions, separate OCR labels and complete mixed index publication/citations.
Actual native workflow success and known image-model omissions are recorded in
`sprint4/frame-descriptions.md`. The owner's stack/defaults were not changed;
configured availability is not readiness or model-quality approval.

1. Independent review of owned/licensed real examples for visual retrieval/code
   quality and audiovisual source/timing correctness. User assertions and tiny
   synthetic probes are not representative quality or verified alignment.

The repository currently has authored subtitle/frame JSON examples and synthetic
evaluation fixtures, but no corresponding real recording or human acceptance
record. The 10-video partial-failure/resume software check is already recorded in
`sprint4/validation-record.md`; it does not need another implementation.

To begin the remaining review, supply an owned/authorized short screen recording
and its matching SRT/VTT privately, with expected answers and relevant times noted
before inspecting model output. Include code/terminal and visual-only information;
a single clip starts the review, not a representative quality claim. Use existing
gallery/timeline/citation views and evaluation tools, then record observed errors
and the human acceptance decision in the existing validation records. Do not
publish private media, labels, excerpts or content fingerprints without explicit
permission. No new evaluator, model download or owner-stack change is required.

The consolidated checklist is `sprint4/implementation-plan.md`. Existing measured
one-digit/sub-second misses, cursor noise and mixed-language OCR errors remain
visible in `sprint4/code-policy-evaluation-validation.md`; uniform stays default.
The paired diagnostics and timeline are included in that green hosted baseline.
It does not certify subsequent changes until their exact hosted run is verified.

The local onboarding follow-up adds a standard-library-only, read-only
`scripts/check_local_setup.py` command and startup troubleshooting in the README.
It diagnoses prerequisites without changing credentials, permissions, services
or data; optional profile/model readiness and real-example quality remain separate.
This usability improvement adds no new Sprint 4 closure requirement.

The delivery-recovery follow-up preserves subtitle/metadata drafts and replay keys
after failed acceptance delivery, and keeps chat replay keys if a conversation
switch fails. Only accepted source requests reset their form; source-list refresh
failure remains distinct. No new provider, persistence class or quality claim.

Project create/rename forms also preserve attempted names after returned errors,
lock pending edits and show the server's canonical accepted rename. Draft state is
keyed by project, with existing server authorization unchanged. This is correction
UX, not idempotent project creation or a new release/quality gate.

The static `/demo` walkthrough makes the existing default keyless path easier to
try: MIT-licensed authored subtitle download, manual permission/upload, supported
and unsupported questions, actual chunk-level citations, saved history and confirmed
demo-only cleanup. It creates no records, changes no settings and includes no real
recording. It supports the selected v1 workflow acceptance and does not replace
independent quality review.

The project page now shares successful source-list updates with chat: newly published
sources become selectable without a page reload. Failed refreshes preserve the last
usable list; missing/incompatible selections cannot silently widen to all sources.
Chat drafts, uncertain-delivery replay keys and version-pinned history survive these
updates, while navigation to another project resets the client scope.

Confirmed source removal now also hides each complete chat turn citing that source,
matching the existing server-side deletion cascade. Monotonic scoped removal fences
reject late history/SSE and stale source refreshes without confusing reindexing with
deletion or treating an initial source-list error as proof of removal. This changes
the open browser view, not the independently tracked physical-file cleanup or the
fact that data already received/copied by a user cannot be recalled.

Before enabling Sprint 5 generation, resolve the remaining extension and official
documentation behavior in `07-open-decisions.md`. Explicit source/preferences
contracts can precede those choices; they do not declare the sprint implemented.
