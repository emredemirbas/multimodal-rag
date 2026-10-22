# Private resumable ASR checkpoints

Date: 2026-10-21
Status: Implemented and locally validated; first durable component of ADR 0018
slice B. See `asr-checkpoints-validation.md`. Product WAV upload remains disabled.

Continue the approved WAV-only/local-only scope without prematurely enabling
product audio upload. This delivery implements private PostgreSQL window staging
and deterministic derived-VTT assembly, not the whole media ingestion workflow.

- Migration 0010 ties an immutable input/model/language/assembly profile and at
  most twenty 30-second windows to an existing scoped `asr` job/source/generation.
- Begin/save/assembly require the live project, initiating membership, source
  generation, job type, claim token and unexpired lease. Reopening a run verifies
  the original WAV digest/frame count and model/profile; changed input fails closed.
- Strictly validate each result again before committing it. Advance an ordered
  cursor once per accepted window; duplicates cannot overwrite text or count usage
  twice. Worker loss/retry preserves committed windows, not in-flight inference.
- Keep staging outside published transcripts, retrieval, citations and usage_events.
  Persist actual accepted frame/model-duration counts and immutable provenance;
  do not fabricate token counts, paid cost or broad speech-recognition quality.
- Assemble only complete runs. Preserve absolute timestamps and silent windows;
  all-silent input fails explicitly. Escape/control-normalize text and verify the
  VTT against existing subtitle limits before returning an immutable artifact.
- This component performs no object PUT, model request, source activation or
  database job completion. Ordinary ingestion claims reject ASR jobs. Source and
  project deletion cascade through staging; stale claims cannot recreate it.
- Test isolated PostgreSQL migration/preservation, concurrency, loss/retry,
  tenant/project/source/generation/membership fences, corruption and deletion.

No API/BFF/form accepts WAV, no new audio retention is started, and no live user
source is created by this delivery. The dedicated media worker/queue, durable raw
artifact cleanup, atomic derived-object adoption and machine-generated source UI
remain required before the application can enable audio upload. No new paid
service, model download, broader media input, commit or push is implied.
