# Delivery status and finish lines

Date: 2026-10-28. Hosted code baseline: `f99b86a`. These are planning estimates, not a
completion percentage, delivery promise or background-work schedule.

## Where we are

The project is in **Sprint 4**, not finished Alpha 2. Project/auth/isolation,
authorized subtitle jobs, scoped retrieval/chat/citations, optional free local
answers/embeddings, ordered playlist relationships, constrained WAV transcription
and constrained MP4 -> retained frames/OCR -> indexed frame citations exist.
Optional explicitly pinned local image-model descriptions now feed separately
labelled versioned visual evidence, with inspectable uncertainty and recovery.
Media uploads are independently opt-in; configured availability is not readiness
or quality. Original retirement/verified cleanup and complete deletion are tested.

The `f99b86a` code baseline passes all four hosted CI jobs, including the new
description workflow and real worker/checkpoint recovery:
[run 40593035299](https://github.com/emredemirbas/multimodal-rag/actions/runs/40593035299).
Software test counts are not representative ASR/OCR/RAG quality approval. Known
mixed-language OCR/ASR vocabulary limitations remain in the validation records.

| Work | Current state |
|---|---|
| Sprints 0–2: foundation, projects, transcript ingestion | Implemented and validated within the documented local scope |
| Sprint 3: RAG/chat/evidence | Implemented local baseline plus optional local models; representative quality review remains open |
| Sprint 4: playlist and multimodal evidence | WAV/MP4/OCR, frame citations, opt-in change selection, user-asserted timeline and optional local image descriptions exist; independent real-example audiovisual/quality verification remains open |
| Sprint 5: learning objectives and assignments | Not implemented; product decisions must be resolved first |
| Sprint 6: submissions and hardened deterministic grading | Not implemented; largest technical/security uncertainty |
| Sprint 7: progressive tutoring/deadlines/mastery | Not implemented |
| Sprints 8–9: broader hardening and hosted beta | Portions of safety/observability exist already; production/beta launch is not the selected portfolio target |

## Two possible finish lines (owner choice pending)

The owner selected a free GitHub portfolio, not a production launch. Do not silently
delete the original learning-platform roadmap or report a narrower demo as its
completion. A separate first portfolio release is proposed, not yet selected.

1. **RAG portfolio v1**: reproducible local setup, an owned/licensed demo, working
   transcript/optional media -> scoped answers -> inspectable evidence -> complete
   deletion, clear limitations and polished README/demo. Core flows and fresh-start
   verification must pass. Deferred multimodal capabilities are explicitly named;
   no full Sprint 4/Alpha 2 claim. Estimate: **1–3 active engineering weeks** with
   stable scope, including sample review, UX fixes and packaging. The current app
   already demonstrates much of this loop; this is a release/quality buffer, not
   three more weeks of invented infrastructure prerequisites.
2. **Learning-workspace scope**: finish the accepted multimodal scope, then add
   cited objectives/assignment drafts and approval, immutable submissions, a real
   hardened runner with deterministic results, progressive feedback and progress.
   Estimate: **8–12+ active engineering weeks**, not a hosted production launch.
   Runner isolation/security, local-model quality, hardware and product review can
   extend it. Never substitute ordinary Docker execution to hit an estimate.

Assume regular focused development, unchanged zero-paid-service requirement,
timely review of blocking choices and no major new feature requests. These ranges
are judgement-based planning bands, not measured remaining labor or calendar
automation. Sporadic sessions, CPU limits and human evaluation change elapsed time.
Re-estimate after the owner selects a finish line and after the first runner spike.

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

Before Sprint 5, resolve source selection, difficulty/extension policy and official
documentation behavior in `07-open-decisions.md`; do not silently choose those
questions while declaring that sprint implemented.
