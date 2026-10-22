# ADR 0018: Restricted local WAV transcription foundation

- Status: Accepted scope; foundation implemented, product ingestion still disabled
- Date: 2026-10-21

The owner asked to push and continue after the proposed authorized WAV scope:
20 MB/10 minutes maximum, local inference with no paid endpoint/cloud fallback,
original-audio deletion after success/cancellation/permanent failure, derived
transcript retained. State that continuation interpretation explicitly. Initial
encoding is restricted to signed 16-bit PCM, mono, 16 kHz; no arbitrary AV decoder,
URL download or compressed/video input. Other encodings fail with export guidance.

Deliver in two slices. This ADR's foundation does **not** enable binary registration
or promise terminal cleanup before the durable workflow exists. Product audio upload
remains disabled. The follow-up must add a dedicated media queue, scoped job/window
checkpoints, source/version attribution, atomic transcript adoption, tracked original
cleanup on all terminal paths and full authorization/deletion/retry/UI coverage.

Use application-owned validated slice contracts around private faster-whisper 1.2.1
and CTranslate2 4.8.2, Whisper base multilingual CPU int8. Pin Systran revision
`a80717a3a48b1b28aa687bca146cb7301feae1b1` and all four public file SHA-256 checksums.
The profile includes weights, engine, PCM encoding and decoding options. No model
pull occurs on startup/inference. A separate explicit no-credential installer has
size/hash/redirect checks, atomic adoption and no overwrite of existing weights.

Each request contains at most 30 seconds of validated raw PCM and one language
choice, never application IDs, credentials, prompts or history. Limit one inference,
four connections, 256 generated tokens, 100 segments, 16,000 text characters and
32 KiB JSON. Reject invalid identity, extra fields, nonfinite/boolean probabilities,
overlapping/out-of-window timestamps and mismatched input lengths/languages. Empty
speech output is an explicit valid slice, not fabricated transcript evidence.

The credential-free service has no published port, application/user-data mount or
Docker socket. An internal-only network supports inbound operator/future worker
calls. Bind the listener before installing an inherited, fail-closed seccomp filter
which denies `socket`, `socketpair` and `connect`, including existing threads and
children. The startup probe verifies actual kernel enforcement. This supplements
Docker's default seccomp, dropped capabilities and no-new-privileges; it is not a
substitute for the future hardened learner-code runner.

Use a fresh filtered model subprocess per slice with an allowlisted environment,
35-second wall/30-second soft CPU limits, bounded anonymous tmpfs output and no core
dumps. Original PCM crosses stdin only, never a file. No model/session memory is
retained between slices. Two CPU cores, 2 GiB RAM/no swap, PID and tmpfs limits,
read-only root/weights and bounded client timeouts complete the local resource
boundary. Slow/busy/missing/invalid inference fails honestly, without provider retry
or fallback. Recognized text/raw errors are not logged. Unknown token usage remains
unknown; no usage rows are fabricated before durable ingestion exists.

Tests use fake local HTTP/model setup data and an actual isolated seccomp probe.
Report native model tests separately. A short synthetic voice probe is not a broad
ASR/timestamp or multilingual quality guarantee. Default CI/startup downloads no
weights and cannot accept binary audio. See `../sprint4/local-asr-plan.md`.

The first slice-B component adds migration 0010 private ASR windows and complete-run
VTT assembly under the existing live actor/project/job/generation/lease fences.
Pin original SHA-256/frames, model and assembly profile and language; reject drift,
duplicate/out-of-order writes and incomplete/corrupted output. Keep accepted window
counts/model durations separate from published usage/evidence. All-silent input
must not invent speech. This component stores no original WAV, calls no model and
creates no public upload/job; original cleanup, dedicated queue execution and atomic
derived-object adoption remain required before exposing audio. See
`../sprint4/asr-checkpoints-plan.md`.

References: [official implementation](https://github.com/SYSTRAN/faster-whisper),
[pinned public model](https://huggingface.co/Systran/faster-whisper-base/tree/a80717a3a48b1b28aa687bca146cb7301feae1b1),
[libseccomp rules](https://man7.org/linux/man-pages/man3/seccomp_rule_add.3.html).
