# Compare uniform and change-aware OCR without hiding losses

This operator-only diagnostic changes no application policy, record or upload flag.
Uniform remains default. Results are measurements, not representative quality,
compiler correctness, scene recall or an automatic policy recommendation.

## Reproduce the five authored probes

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.code_suite
```

To inspect one fixed case, append `--case single_digit` (also `terminal_error`,
`cursor_motion`, `subsecond_view`, `turkish_code`). All clips/text/schedules are
original authored fixtures, not downloaded recordings. Text labels are declared
before OCR and cover the complete visible text/schedule. Source is in
`backend/app/vision/code_suite.py`. The five simple monospace grayscale views are
not a real terminal/IDE corpus. Sub-second/small edits and irrelevant cursor motion
are intentional negative cases, not errors to remove from the report.

The tool generates temporary supported MP4s, verifies their expected metadata,
runs actual local FFmpeg/Tesseract under both fixed policies and prints content-
free JSON. Both policies use identical OCR engines/language data/requested language.
Clip/label/result hashes, exact PTS, coverage gains/losses and literal identifier/
OCR counts remain; no raw text, code, identifiers, images or paths are exported.
All measurements, including poor ones, are retained; valid poor diagnostics exit
zero. No overall winner or reviewed quality threshold. See the separate validation
record for measured successes **and failures**.

## Compare an owned/authorized clip with independent labels

Prepare a `visual-reference-v1` file using `visual-evaluation-guide.md`: exact MP4
digest/byte count/metadata, <=20 ordered disjoint intervals, complete visible text
and optional literal identifiers. Inspect labels independently of recognized OCR.
Keep private clips, labels and reports outside the checkout; hashes can still
identify content. A `human_reviewed` field is a declaration, not certification.

```bash
docker compose --profile visual-tools run --rm -T --no-deps \
  --volume /absolute/path/to/reference.json:/reference.json:ro --entrypoint python \
  visual-inspect -m app.vision.compare --authorized-input --language en \
  --reference /reference.json < /absolute/path/to/owned-tutorial.mp4
```

Make only that label file readable by UID 1000; never mount a secret/general data
directory. Existing media/isolation/resource bounds apply. Rights/arguments are
required before reads; byte/digest binding is checked before native processing.
Metadata mismatch after uniform stops before the second native call. Both results
must bind to the same validated label snapshot, exact input and OCR family; policies
must be uniform v1 then change v2. No fallback, model/download, app credentials or
export API. The two sequential native calls retain their existing per-call limits;
comparison costs two extractions, not one. Complex clips may time out.

## Interpret paired measurements

- `coverage_changes` lists gained/lost/shared/missed-by-both **interval ordinals**,
  using retained actual PTS inside half-open labels. This is not semantic scene
  recall or inferred visibility. Equal total coverage can hide a changed interval
  being lost while a return interval is gained.
- `measurements` preserves both full single-policy diagnostics. Every labeled
  retained frame contributes; different sampling weights mean overall WER/CER
  differences alone do not identify the better policy. Missing intervals have no
  invented perfect OCR score. Always read coverage and OCR together.
- `common_image_ocr` separately scores labeled frames at identical actual PTS
  with identical **decoded pixels**, not necessarily identical PNG compression.
  A pixel conflict fails the pair instead of quietly omitting it. The timestamp
  list includes unlabeled common points too; only labeled ones enter OCR counts.
  No scored shared points means zero counts/null rates, not zero error.
- Shared OCR uses micro-aggregated counts from those exact samples, with no new
  alignments. Total word/normalized/literal edit work across **both** policies is
  preflighted to 8,000,000 cells before either is scored. Old single-policy
  diagnostics and normalization are unchanged.
- Literal CER retains case/spacing/punctuation differences; identifier recall
  checks only listed spellings, not syntax, order or execution. For example, high
  identifier recall can coexist with broken parentheses/indentation or a wholly
  missed changed interval. Never execute the recognized code as a quality test.

The tools have no project-owned records and no application access. Temporary native
files are removed with their owned contexts/container. They do not restart the
owner's services, enable change mode or increase current resource/retention limits.
