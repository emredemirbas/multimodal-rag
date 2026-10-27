# Sprint 4 — implementation and finite closure checklist

Updated: 2026-10-28. The original playlist slice is in `validation-record.md` and
ADR 0014. This is the consolidated current plan, not a fresh sprint for every
supporting component. Full multimodal/Alpha 2 is not yet approved.

## Delivered application flows

- Ordered playlist snapshots, explicit authorized transcript/lesson associations,
  bounded per-video concurrency, partial failure and independent retry/resume.
- Optional restricted local WAV -> isolated ASR -> retained transcript/index,
  resumable jobs, immutable processing provenance and verified original cleanup.
- Optional restricted MP4 -> isolated native frame/OCR -> durable gallery ->
  indexed frame evidence/citations; atomic outbox handoffs, recovery and complete
  source/project deletion. Public upload/retention UI is independently default off.
- Default uniform/exact-pixel selection plus experimental opt-in change selection,
  pinned identities/manifests/actual PTS. Paired authored measurements preserve
  known one-digit/sub-second misses and cursor noise, not a quality endorsement.
- A read-only **frame/transcript timeline** from the retained gallery, with an
  explicit user-asserted recording relationship, signed offset, half-open span
  matching, unmatched states, old-generation links and distinct source origins.
  This does not verify source identity or semantic agreement, persist a pairing
  or silently modify retrieval. See `timeline-alignment.md` for scope/validation.
- Optional local Qwen3.5 vision descriptions of retained frames: explicit digest/
  setup, separate bounded jobs/checkpoints, strict structured output, inspectable
  uncertainty/abstention and automatic labelled OCR/description indexing. Old
  evidence survives; exact model/generation provenance and full deletion apply.
  See `frame-descriptions.md` for native failures as well as software success.

Keep the owner's zero-paid-service portfolio target (ADR 0015), upload opt-ins,
existing formats/languages/resource limits and retention. Metadata uses only the
official allowlisted adapter and never implies downloading rights. No model
download, enabled capability or running owner-stack change is incidental.

## Remaining full Sprint 4 gates — do not grow this list with optional experiments

- [x] **Structured image-model descriptions** with a free local application-owned
  provider, versioned provenance, useful failure/recovery and inspectable frame
  evidence. Implemented behind an independent default-off flag, explicitly pinned
  installed model and separate worker. No download, OCR relabelling or paid fallback.
- [ ] **Independent quality and audiovisual verification** on owned/licensed real
  examples: code/terminal/visual-only questions, relevant-frame retrieval,
  deduplication and transcript/frame source/timing correctness, including known
  failures. Human review and any acceptance threshold must be recorded honestly.
  Current synthetic diagnostics and user assertions do not satisfy this gate.

The original exit still requires a 10-video playlist to process/partially fail/
resume, relevant visual benchmark evidence and suppressed duplicates. Preserve
existing software/native workflow evidence in the validation records; do not
equate passing software counts with representative quality. Additional selection
prototypes/evaluator infrastructure are not new closure prerequisites unless a
specific regression requires them. Fix defects and finish the independent review
gate; do not treat the completed description slice as representative quality.

## Decisions before the next sprint

Do not silently reduce the original learning-platform roadmap to a smaller demo.
The portfolio-v1 versus full learning-loop finish line remains the owner's choice
in `../09-delivery-status.md`. Before Sprint 5, resolve difficulty/extensions,
source selection and official-document retrieval behavior in `../07-open-decisions.md`.
The current timeline view makes none of those choices.
