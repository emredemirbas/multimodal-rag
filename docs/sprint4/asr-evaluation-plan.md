# Local ASR quality diagnostics

Date: 2026-10-23
Status: Implemented within the existing experimental <=30-second WAV probe
boundary. Verification and limitations are in `asr-evaluation-validation.md`.

## Scope and assumptions

Continue the approved local WAV slice with reproducible quality measurement, not
new formats, video/OCR, assignment work or automatic feature enablement. Existing
software/native pipeline tests do not establish speech quality; the earlier
`endpoint` diagnostic remains a recorded failure.

Add an offline reference/result evaluator and an explicit reference option to the
existing native smoke command. References are operator-owned local JSON, bound to
the exact WAV SHA-256 and input-frame count. Native evaluation must verify that
binding **before** calling the existing private model interface. No model download,
cloud call, application database/queue/object access or transcript export is added.

Label status is declared (`synthetic`, `unreviewed`, `human_reviewed`), not an
independent review certificate. Commit only small authored synthetic fixtures.
Real recordings, labels and model text must stay outside the repository; neither
successful measurement nor a synthetic zero error rate approves model quality.
No release threshold is silently selected.

## Measurements and safety

- Version a deterministic English/Turkish normalization policy: NFC, Turkish
  dotted/dotless-I handling, case folding, punctuation/symbol separation except
  underscore, collapsed whitespace; preserve diacritics and word boundaries.
- Report word/character Levenshtein errors and denominators (CER includes the
  normalized spaces). Do not clamp rates above one. Empty-reference rates are
  null; report inserted words/characters and explicit silence hallucination.
- Check declared technical identifiers separately as case-sensitive, literal,
  delimited strings; normalization must not turn code spelling into a pass.
- Measure optional unique phrase anchors against their enclosing ASR cue bounds.
  Report missing/ambiguous anchors and coverage separately from scored timing
  error. This is a cue-boundary proxy, **not word alignment** or visual alignment.
- Validate strict schemas, duplicate JSON fields, finite values, input/timeline
  limits and bounded alignment work before scoring. Never skip a mismatched clip.
- Output only content-free metrics, input hashes and pinned model/profile metadata;
  no reference/recognized text, identifier/anchor strings, paths or raw exceptions.
  The tool writes no files. Operators may deliberately save aggregate reports.

## Verification

Use hand-computable insert/delete/substitute, Unicode/Turkish, technical-identifier,
silence, timing coverage/ambiguity, hash/frame mismatch, invalid/oversized input
and secret-free CLI/native-probe tests. Compare the distance implementation with
an independent small exhaustive oracle. Run the ordinary non-integration backend
regression and the fixture CLI; native quality must remain separately reported.
No schema migration, UI, identity/storage boundary or `.env` change is needed.
