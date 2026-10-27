# Measure selected-frame coverage and OCR locally

Date: 2026-10-27.

This explicit operator tool diagnoses one already supported, authorized MP4. It
does not enable uploads, read application projects, export OCR/frames, download
models/datasets or change sampling. Keep real videos, labels and candidate JSON
outside the checkout. Reports contain content fingerprints: do not publish them
for private clips. No metric below establishes a release threshold or quality approval.

## Offline authored example

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.vision.evaluate \
  --reference backend/tests/fixtures/visual-evaluation/reference.json \
  --result backend/tests/fixtures/visual-evaluation/result.json
```

These deliberately imperfect **JSON-only synthetic** fixtures have no corresponding
recording or native inference. The `a` input digest and 1,000-byte count are
placeholders. Coverage is 2/3 intervals; identifier recall is zero; one blank
label has unexpected OCR. Prose-normalized text hides case/slash differences in
the first frame, while its literal CER is 5/19. Aggregate WER is 1/3, normalized
CER 10/18 and literal CER 15/19, including insertions from the blank label.
`input_binding` is only `declared-reference-result`.

The result envelope uses `visual-result-v1`, an `input_bytes` count and a `result`
matching the strict existing private `WireResult` contract (including PNGs and
processing identity). A summary or gallery response is not that contract. There
is intentionally no application-result export endpoint/command. Do not fabricate
offline JSON as native evidence; use the native reference option below for owned clips.

## Prepare labels independently

Inspect an owned, authorized or appropriately licensed clip before looking at
recognized OCR. All existing input limits apply: non-fragmented H.264/avc1 yuv420p
MP4, <=100 MB / 600 seconds, <=1080p/60fps, zero-based/unrotated timeline; optional
AAC ignored. The existing authorized stateless probe reports exact input SHA-256
and video metadata without exporting recognized text. Count host file bytes with
`wc -c < /absolute/path/to/owned-tutorial.mp4`.

Write a UTF-8 reference JSON outside the repository. Replace the digest, byte count
and **all video metadata** with this exact clip's values. This structure is an
illustration, not a real input fingerprint:

```json
{
  "schema_version": "visual-reference-v1",
  "label_status": "unreviewed",
  "input_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "input_bytes": 1000,
  "video": {
    "duration_ms": 20000,
    "width": 960,
    "height": 540,
    "fps_numerator": 2,
    "fps_denominator": 1
  },
  "intervals": [
    {
      "start_ms": 0,
      "end_ms": 10000,
      "language": "en",
      "text": "Use FastAPI /health",
      "identifiers": ["FastAPI", "/health"]
    },
    {
      "start_ms": 10000,
      "end_ms": 20000,
      "language": "tr",
      "text": "SAĞLIK KONTROLÜ"
    }
  ]
}
```

Each interval labels the **complete visible OCR target** throughout a stable view,
not one word cropped from a larger screen. Use ordered disjoint `[start_ms,end_ms)`
intervals within the video; gaps are allowed and adjacent boundaries belong only
to the later interval. Split changing text into separate intervals. Supply up to
20 intervals, <=4,000 characters and <=32 distinct literal identifiers each.
Use `"text": ""` explicitly for blank views; punctuation-only code labels are valid.
Language selects English/Turkish text normalization, not automatic OCR detection.

`synthetic`, `unreviewed` or `human_reviewed` is a declaration; this tool cannot
verify rights, label accuracy or independent human review. A reference copied from
the OCR output is not an independent accuracy measurement. Do not label secrets.

## Native evaluation in the existing isolated tool

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps \
  --volume /absolute/path/to/reference.json:/reference.json:ro \
  visual-inspect --authorized-input --language tr \
  --reference /reference.json < /absolute/path/to/owned-tutorial.mp4
```

Make only that reference readable by UID 1000; do not broadly change directory or
secret permissions. Only MP4 bytes enter stdin; the host clip is not deleted.
The reference is mounted read-only into the ephemeral operator tool, not the
application's native service. Existing no-network, non-root, read-only, tmpfs,
kernel/child and CPU/memory/PID/time restrictions remain. The tool writes no
export/report file; native temporary files disappear with its owned contexts.

Digest and byte count are checked **before** native inference; expected video
metadata is checked against validated extraction **after** inference. Mismatch
fails safely, not by skipping bad labels. A successful native report records
`verified-mp4-bytes`. Choose existing explicit `en`, `tr`, or experimental `en+tr`;
per-interval language compatibility is reported independently of accuracy. Do not
combine `--reference` with the old fixture-specific `--synthetic-card-check`.

## Read the report

- Sampling coverage counts intervals containing at least one **retained actual
  PTS**, never requested sample time or an inferred duration. Missing intervals
  remain visible; all-missing OCR rates are null, not zero. This is a temporal
  sampling diagnostic, **not scene recall** or proof that pixels match the label.
  Exact deduplication may remove a later identical view. Repeated views and short
  code changes therefore require careful interpretation, not nearest-frame matching.
- Every retained frame inside an interval is scored; none is selected for the
  best OCR score. Aggregate counts/rates are micro-aggregated over these samples,
  not over duration or unique scenes. Long intervals with more selected frames
  contribute more. Missing intervals are excluded from OCR denominators: always
  read coverage with the OCR scores. Unlabeled retained frames are counted separately.
- WER/CER use the existing `nfc-en-tr-words-v1` normalization: NFC, Turkish I/İ
  handling for `tr`, case folding, punctuation/symbol separation except underscore
  and collapsed whitespace. CER includes normalized spaces. This helps compare
  prose but can hide important code errors.
- `literal_cer` uses **NFC only**, case-sensitive, preserving punctuation, spaces
  and line breaks. It is not a syntax/compiler check or byte identity: composed
  versus decomposed Unicode is equivalent. Different line wrapping still counts
  as a literal error. Literal identifiers are separately case-sensitive/delimited
  with no normalization; recall is at-least-once per identifier per sampled frame,
  not precision, frequency, order or code correctness.
- Edit rates are unit-cost Levenshtein edits/reference units and may exceed one.
  Empty denominators yield null. Insertions remain in counts and aggregate
  numerators. `blank_with_text` flags any nonblank recognized text, including
  punctuation, for an explicitly empty reference. Whitespace-only OCR is not text.
- Reports contain ordinal/time/counts, image/input/label/result hashes and full
  engine/language-data/profile identity; no OCR/label/identifier strings, pixels,
  filenames or raw exceptions. Different profiles/labels/normalization are
  different experiments. A valid poor diagnostic exits zero;
  `quality_approval` always stays `not_established`.

Reference JSON is bounded to 128 KiB; result JSON to 18,001,024 bytes and the
existing <=20 bounded PNG/OCR wire contract. Total word, normalized-character and
literal-character alignment work across all samples is capped at 8,000,000 cells
**before scoring**. Use fewer/shorter labels if rejected; do not silently omit
failing intervals. Duplicate JSON keys, nonfinite values, extra fields, invalid
PNG/hash/profile/timelines or mutated models fail closed with safe output.

## Still required for quality claims

Native authored English/Turkish card diagnostics are recorded separately in
`visual-evaluation-validation.md`, including the existing combined-language
failure. They are not real-terminal/code/slide, brief-scene, long-input or
representative OCR benchmarks. Review a diverse independently labeled corpus
before selecting quality thresholds or changing the sampling policy. No vision
description, verified transcript/frame alignment or full Sprint 4/Alpha 2 claim.

The follow-up `code-policy-evaluation-guide.md` adds an explicit same-clip paired
operator command and five authored code/terminal probes. It keeps this evaluator's
single-policy metrics unchanged, preflights both policies' combined edit work and
reports interval losses alongside gains plus identical shared-PTS OCR. It does not
turn this small authored set into a representative reviewed benchmark.
