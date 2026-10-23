# Local ASR diagnostics validation

Date: 2026-10-23
Status: Local software and isolated native diagnostic verified. Hosted CI is
separate and not claimed as passed in this pre-push record. No representative
speech-quality or full multimodal/Alpha 2 approval.

## Delivered

- Offline `python -m app.asr.evaluate` accepts strict bounded reference/result
  JSON; the existing native probe adds explicit `--reference`.
- Versioned English/Turkish normalization, word/character edit counts/rates,
  separate literal technical-identifier recall, silence hallucination and optional
  unique-phrase enclosing-cue boundary diagnostics with explicit coverage.
- Native SHA-256/frame binding before inference; offline binding clearly declared.
  Label-review status is declared, not verified. Reports include immutable input/
  label/result hashes and pinned model identity but no recognized/reference text,
  identifiers, anchor strings, private paths or raw exceptions.
- Missing labels/null denominators and poor scores are not converted into success.
  Valid measurements exit zero, with `quality_approval: not_established` always.
  No hidden release threshold or automatic corpus/model download.

## Software evidence

The focused suite has **48 passing cases** (0.51s). It covers hand-computed
insert/delete/substitute rates, scores above one, silence including punctuation-only
output, NFC/Turkish case handling and diacritics, identifier case/boundary/escaping,
anchors spanning cues, unmatched/ambiguous anchors and all-label denominators.
An independent recursive oracle checks every pair of binary strings through
length four, and token-sequence variants, against the edit-distance implementation.

Negative cases include duplicate/oversized/invalid JSON, NaN/Infinity, unexpected
fields, invalid labels/controls/timelines/profile, mutated model instances,
hash/frame drift, bounded alignment work before scoring and safe CLI failure.
The native-probe unit test counts one controlled provider call and verifies no
text export; the unchanged ordinary smoke keeps its prior content-free contract.
Mutually exclusive diagnostic options fail before reading audio.

The final full backend regression passed **324 tests, no skips, in 98.65s**,
including actual PostgreSQL authorization/version fences, Redis/Celery process
recovery and MinIO lifecycle checks. It ran with allowlisted test credentials in
three newly created disposable service containers, fresh tmpfs data and no
application data mounts or `.env` access. Only those exact new containers were
removed afterward. Frontend source/dependencies are unchanged in this slice.

The committed, deliberately imperfect **JSON-only** example was executed via the
offline CLI: WER 0.25 (1/4), CER 0.296296 (8/27), identifier recall 0 and timing
coverage 0 with one missing anchor. Its placeholder digest, candidate and labels
are synthetic; this is not a corresponding audio/model-quality experiment.

## Actual native evidence

A separately tagged production ASR image built successfully. A new internal
Docker network and newly created server/probe containers used only the existing
approved public weights **read-only**. They had no published ports, application
credentials, database/Redis/object access, original-media volume or Docker socket.
The server retained non-root/read-only/capability-drop/no-new-privileges, 2 CPU,
2 GiB/no extra swap, 64 PID, tmpfs and inherited model-child seccomp restrictions.
The reference JSON was mounted read-only into the separate probe, not the server.

The fixed, implementation-authored English flite `slt` phrase was the same one used
in the earlier upload/playlist probe. Trusted FFmpeg synthesis produced PCM in
memory; a canonical stdlib WAV wrapper was **176,204 bytes / 88,080 frames**
(5.505s), SHA-256
`91897886306f0188eb04fb3e2472149b86ec225f4f8c2d44ba0ab48ae5e117eb`.
Reference text/digest/frame count were fixed before inference.

1. A deliberately wrong digest exited 1 with no transcript/raw error; the private
   server's completed-inference event count remained **zero**.
2. The matching reference exited 0 and reported `verified-wav-bytes`, synthetic
   labels, matching English, 14 reference/recognized words, 81 normalized
   characters, **WER 0 / CER 0**, and **1,622 ms** model-child duration. Exactly
   **one** native inference-complete event was observed.
3. No identifiers or human timing anchors were supplied: their rates/coverage
   remained **null**, not a passing technical/timestamp test. The report retained
   `quality_approval: not_established` and did not print the recognized text.
4. Only newly returned exact container/network IDs were removed afterward. The
   pre-existing application, its configuration/data and public weights were kept.

This short synthetic success does **not** resolve the earlier failed native
`endpoint` diagnostic. No new natural-speaker, Turkish ASR, noise, technical-code,
cross-window or independently labeled timing-quality result is claimed. The
Turkish tests verify deterministic evaluator behavior, not native Turkish accuracy.

## Boundaries

No database migration, schema/data reset, dependency/version, frontend, production
identity/provider, upload default or original-retention change. Actual `.env`
remains ignored and mode 0600; application services were not restarted. WAV upload
stays opt-in false by default. MP3/MP4/video/frame/OCR, assignments and release
thresholds are unchanged/open. See `asr-evaluation-guide.md` for safe operator use.
