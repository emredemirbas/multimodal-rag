# Delivery status and finish lines

Date: 2026-10-27. Hosted baseline: `f719635`. These are planning estimates, not a
completion percentage, delivery promise or background-work schedule.

## Where we are

The project is in **Sprint 4**, not finished Alpha 2. Project/auth/isolation,
authorized subtitle jobs, scoped retrieval/chat/citations, optional free local
answers/embeddings, ordered playlist relationships, constrained WAV transcription
and constrained MP4 -> retained frames/OCR -> indexed frame citations exist.
Media uploads are independently opt-in; configured availability is not readiness
or quality. Original retirement/verified cleanup and complete deletion are tested.

That baseline passes all four hosted CI jobs:
[run 40569511282](https://github.com/emredemirbas/multimodal-rag/actions/runs/40569511282).
Software test counts are not representative ASR/OCR/RAG quality approval. Known
mixed-language OCR/ASR vocabulary limitations remain in the validation records.

| Work | Current state |
|---|---|
| Sprints 0–2: foundation, projects, transcript ingestion | Implemented and validated within the documented local scope |
| Sprint 3: RAG/chat/evidence | Implemented local baseline plus optional local models; representative quality review remains open |
| Sprint 4: playlist and multimodal evidence | Constrained WAV/MP4/OCR and experimental opt-in change-aware selection exist; descriptions, verified transcript/frame alignment and representative evaluation remain open |
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

## Next bounded step

Continue the existing Sprint 4 plan while that choice is pending. The isolated
candidate prototype is complete within its documented scope and its hosted checks
are green; see `sprint4/scene-selection-validation.md`. The following private
v2 selection-manifest/checkpoint component (ADR 0027/migration 0018) preserves all
bounded score/hash records, revalidates ranking, keeps legacy digests and supports
temporal-return gallery/index/citation provenance. See
`sprint4/selection-manifest-plan.md` and its separate validation record.

The next native integration is now implemented as ADR 0028: actual scan/selected
OCR -> pinned v2 service/worker -> existing managed evidence, with real fractional
source-FPS/PTS and authored public upload/citation/cleanup probes. See
`sprint4/change-ocr-validation.md`. Uniform remains the default; no change was
enabled on the owner's stack. The hosted baseline above is not a CI result for
this subsequent producer follow-up.

Next broaden owned/authored code/terminal cases and compare the two policies with
explicit labels/identifier and frame-coverage diagnostics. Representative quality,
descriptions and verified audiovisual alignment are still open. Do not equate
this tiny authored transient success with full scene understanding or Alpha 2.

Before Sprint 5, resolve source selection, difficulty/extension policy and official
documentation behavior in `07-open-decisions.md`; do not silently choose those
questions while declaring that sprint implemented.
