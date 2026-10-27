# Local selected-frame and OCR diagnostics

Date: 2026-10-27. Scope: the already accepted stateless MP4/OCR operator probe.
Status: Implemented and locally verified; see `visual-evaluation-validation.md`.

Continue Sprint 4 with measurement before changing the sampling algorithm or
adding a vision model. This is not a representative quality benchmark, scene
detector, application export/API, new retention class or automatic enablement.
Keep existing formats, limits, native isolation and default-off upload unchanged.

Material assumptions:

- Operator-owned labels bind to exact MP4 SHA-256, byte count and expected video
  metadata. Native evaluation checks bytes before any native call and metadata
  after extraction. Offline JSON binding is only declared, not independently
  verified. Labels/review status are declarations, never review certification.
- At most 20 ordered, disjoint half-open time intervals label all visible text
  within each interval, with explicit English/Turkish normalization language and
  optional literal identifiers. Intervals must be chosen before seeing OCR.
  Empty text explicitly labels a blank frame. Keep real clips/labels/results
  outside the checkout; commit only authored JSON fixtures.
- Coverage is **retained PTS inside labeled intervals**, not scene recall or
  proof that the retained pixels depict the intended scene. Deduplication can
  remove a later identical view; do not infer its duration or match a nearby frame.
  Report missed intervals separately from OCR scores on sampled frames.
- Score every retained frame within an interval, never pick the best OCR result.
  Report micro-aggregated normalized WER/CER, case-sensitive NFC-only literal CER,
  literal identifier recall and unexpected OCR on blank labels. Missing samples
  have no fabricated OCR score; zero denominators remain null, rates may exceed 1.
  Punctuation/case/whitespace differences remain visible in literal CER.
- Strict bounded JSON/PNG/profile/timeline validation, duplicate-field rejection,
  preflight total edit-work limit and content-free reports/errors. Reuse the ASR
  evaluator's unchanged pure text metrics through a small shared module.
- Add an offline CLI and mutually exclusive `--reference` option to the existing
  authorized native probe. No project/database/queue/object/provider credentials,
  result exporter, download or paid request. Reports retain input/label/result
  fingerprints, identity and ordinal/timing/count diagnostics, not text or paths.

Verify arithmetic, coverage boundaries/missing intervals/dedup caveat, multilingual
normalization versus literal code differences, blank labels, aggregate work limits,
mutated/bad contracts and safe CLI output. Exercise actual isolated native cards
with fixed-before-inference labels separately from synthetic software fixtures.
No quality threshold is selected; `quality_approval` stays `not_established`.
