# Measure local ASR without publishing transcripts

Date: 2026-10-23

This explicit operator tool measures **one labeled <=30-second supported WAV**.
It does not download models, enable uploads, access application projects, fetch
datasets, export recognized text or write files. No extra dependency is needed.
Keep private recordings, labels and candidate results **outside the repository**.
Reports contain content fingerprints and should not be published for private clips.

## Offline synthetic example (no model or services)

From the repository root, with the existing backend environment installed:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.asr.evaluate \
  --reference backend/tests/fixtures/asr-evaluation/reference.json \
  --result backend/tests/fixtures/asr-evaluation/result.json
```

The deliberately imperfect authored JSON fixture has WER **0.25** (one edit / four
reference words), technical-identifier recall **0** and timing coverage **0**.
There is no corresponding recording or actual model run: the repeated `a` digest
is a placeholder, labels are `synthetic`, and `input_binding` is
`declared-reference-result`. This tests the evaluator, **not Whisper quality**.

Offline results use `asr-result-v1`, the claimed exact WAV digest and a `result`
object matching the pinned `TranscriptionSlice` contract. Never fabricate these
files as native evidence. This tool intentionally has no recognized-text exporter.

## Prepare a real reference

Use an owned, authorized or appropriately licensed WAV under the existing limits:
signed PCM16, 16 kHz, mono, <=30 seconds. Prepare the reference independently of
the model output. An operator can inspect the exact input without printing text:

```bash
PYTHONPATH=backend backend/.venv/bin/python - /absolute/path/to/owned-probe.wav <<'PY'
import hashlib, json, pathlib, sys
from app.asr.wav import MAX_WAV_BYTES, SLICE_FRAMES, validate_wav
with pathlib.Path(sys.argv[1]).open('rb') as stream:
    content = stream.read(MAX_WAV_BYTES + 1)
wav = validate_wav('owned-probe.wav', content)
assert wav.frames <= SLICE_FRAMES, 'Use at most 30 seconds'
print(json.dumps({'audio_sha256': hashlib.sha256(content).hexdigest(), 'input_frames': wav.frames}))
PY
```

Write a UTF-8 JSON outside the checkout, replacing both binding fields with those
values. Example structure (the example digest/frame count are not real evidence):

```json
{
  "schema_version": "asr-reference-v1",
  "label_status": "unreviewed",
  "audio_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "input_frames": 48000,
  "language": "en",
  "text": "Use FastAPI health endpoint",
  "identifiers": ["FastAPI"],
  "anchors": [{"start_ms": 1000, "end_ms": 2000, "text": "health endpoint"}],
  "timing_tolerance_ms": 250
}
```

Use `en` or `tr` for the spoken reference language. `label_status` is a declaration:
`synthetic`, `unreviewed`, or `human_reviewed`; the tool does not verify authorship,
rights or independent human review. Human labels should be made against the audio,
not copied from the recognized output. Timing tolerance is an explicitly chosen
diagnostic tolerance, **not a project release threshold**. Omit both `anchors` and
`timing_tolerance_ms` if timing has not been independently labeled. Optional
identifiers must appear literally in the reference; do not include secret tokens.
Use exactly `"text": ""` for labeled silence, with no anchors/identifiers.

## Native run against the existing private local service

Perform the README's explicit pinned-weight/local-ASR setup first. Rebuild the
optional image after updating this code; this does not download Whisper weights:

```bash
docker compose build asr
docker compose --profile local-asr run --rm -T --no-deps \
  --volume /absolute/path/to/reference.json:/reference.json:ro \
  --entrypoint python asr -m app.asr.smoke --language en \
  --reference /reference.json < /absolute/path/to/owned-probe.wav
```

The local reference must be readable by the container's non-root UID 1000. The
reference is mounted read-only into the probe, **not the model server**. The probe
checks the WAV digest/frame count before its one call to the existing private ASR
interface. There is no application project/source, queue handoff or retained audio.
The native report says `input_binding: verified-wav-bytes`. `--language tr` or `auto`
selects the existing decoding option; detected-language mismatch is reported, not
silently removed from scoring. Original product retention and normal UI caveats
are unchanged. Do not combine the old fixture-specific keyword flag with a general
reference evaluation.

## Interpret the measurements

WER and CER use unit-cost Levenshtein edits / reference units; values can exceed
one for extra recognized material. CER includes spaces between normalized words.
See the [Hugging Face metric explanation](https://huggingface.co/learn/audio-course/en/chapter5/evaluation)
for the word/character distinction. The versioned application normalization is
`nfc-en-tr-words-v1`: NFC, Turkish `I`/`İ` handling for `tr`, case folding,
punctuation/symbol separation except underscore, whitespace collapse; accents and
word boundaries are retained. This is not a locale-independent benchmark standard.
In particular, `endpoint` and `end point` are **not equivalent**, while ordinary
punctuation differences do not count. Do not compare rates from different label
or normalization profiles as if they were the same experiment.

Technical identifiers use a separate case-sensitive escaped literal match with
non-word boundaries. `/health` versus `health`, `FastAPI` versus `fastapi` and
`user_id` versus `user_id_extra` do not become successful identifier matches merely
because word normalization is permissive. Recall is at-least-once per declared
identifier, not code correctness, precision, frequency or order.

Timing labels must be ordered, non-overlapping, in-clip and unique phrases in the
normalized reference. A unique recognized phrase may span multiple cues; compare
the start of its first containing cue and end of its last containing cue against
the annotation. This **enclosing-cue boundary proxy is not word-level alignment**.
Changed cue segmentation can change it. Missing and repeated recognized phrases
are counted as `missing`/`ambiguous`, never silently paired by ordinal. Mean/max
errors cover only scored anchors; always read coverage alongside them.
`within_tolerance_fraction_all_labels` includes unmatched anchors in its denominator.

Empty reference denominators produce JSON `null`, not a fabricated perfect score
or non-finite number. Inserted word/character counts and `silence_hallucination`
remain visible; any nonblank recognized text, even punctuation-only, breaks labeled
silence. No identifier/timing labels likewise means null rates, not 100% success.

Every report records reference/result/audio hashes, declared label status, pinned
provider/model/revision/profile/engine, language, inference duration and metric
counts. It prints no transcript, label phrases, identifiers, filenames or raw
exceptions. Malformed/mismatched input exits 1 with a generic safe error. A valid
diagnostic exits 0 even for poor scores: `quality_approval` always remains
`not_established`. There is no hidden pass/fail threshold.

Files are bounded to 128 KiB each. References allow 4,000 characters, 32 identifiers
and 16 timing anchors; native output keeps its existing stricter per-cue/window
contract. Total word+character alignment work is bounded to 8,000,000 table cells;
use shorter clips if rejected. Duplicate JSON keys, non-finite values, extra fields,
mutated/invalid timelines, changed profiles and hash/frame mismatches fail closed.

## Representative review still required

The committed fixtures and arithmetic/CLI tests are synthetic only. A future
review should include multiple human speakers in English and Turkish, technical
identifiers/commands, silence/background noise, independently labeled phrase times
and cross-window behavior. Report each group and retain failed cases rather than
selecting only successes. The earlier native `endpoint` failure remains unresolved.
No representative corpus, agreed threshold or full multimodal/Alpha 2 approval is
established by this tooling.
