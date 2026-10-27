# ADR 0029: Explicit local frame descriptions and mixed visual evidence

- Status: Accepted technical continuation of the owner's zero-spend delegation
- Date: 2026-10-28

Use an optional local Ollama Qwen3.5 4B **vision** model on already retained PNGs,
not OCR relabelled as image understanding. The host already has a vision-capable
manifest; this work does not download weights or change the owner's running stack.
Operator setup/enablement and a full expected model digest remain explicit.
`FRAME_DESCRIPTIONS_ENABLED=false` is independent of upload/selection flags.

An authenticated command starts a dedicated Celery description job, one bounded
frame per delivery, with complete scoped checkpoints and retry/cancel/deletion
fences. Pin gallery, actor, model digest, prompt/schema and embedding target at
acceptance; pin the actual local engine before inference. No app identity, OCR,
filename, tools, URLs or credentials enter the prompt. No cloud/pull/fallback,
proxy or redirect. Strict bounded structured output permits abstention, keeps
uncertainty and never establishes code correctness or spoken tutorial coverage.

Only complete descriptions publish. Atomically enqueue the existing text-index
workflow using a new parser version that keeps **separate labelled OCR and model
description chunks**, both anchored to immutable frames/PTS. Preserve v1 parser,
digests, old generations and citations. The new bounded index has at most 300
chunks (280 OCR + 20 descriptions); input/native sampling limits are unchanged.
Index/citation provenance includes the description run/model/engine/prompt, not
mutable current settings. Existing OCR remains active if descriptions fail.

The UI exposes opt-in generation, background progress/recovery, separate OCR and
structured descriptions, uncertainty/abstention and model/version provenance.
Saved answers and evidence distinguish mixed unreviewed visual evidence from
literal OCR; text answers still receive no image or verified visual facts.
Record accepted image count/bytes, tokens when reported, local latency, model and
prompt with zero billed service cost. Complete deletion cascades all new records.

The installed model identity is an operator-pinned manifest, not a promise that a
mutable registry tag still resolves to those bytes. The native engine sees images
in a credential-free separate Ollama process; the dedicated orchestrating worker
has the usual scoped application storage/queue access but does not run native
inference. It is not a code-submission sandbox. Each mixed index pins the whole
description snapshot; the fixed segment text prefixes, not an invented per-chunk
model field, distinguish OCR from descriptions. No model output is a trusted
instruction or a verified statement of tutorial speech.

The description model may hallucinate. Software/native authored probes are not
independent quality approval. The final independent audiovisual/quality gate
remains open; no later-sprint product decision or new experiment is introduced.
Setup, limits and validation are in `../sprint4/frame-descriptions.md`.

References: [Qwen3.5 vision model](https://ollama.com/library/qwen3.5:4b),
[Ollama vision REST input](https://docs.ollama.com/capabilities/vision),
[structured output](https://docs.ollama.com/capabilities/structured-outputs).
