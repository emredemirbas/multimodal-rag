# ADR 0024: Versioned retained-OCR evidence

- Status: Accepted continuation of ADRs 0021–0023
- Date: 2026-10-27

Index literal OCR from a complete retained gallery, not synthetic subtitles or
new native inference. A separate internal command pins gallery and embedding space
in a new job/generation. Eight-document checkpointed batches use the existing
local hash or approved Qwen provider, deadlines and ordinary ingestion queue.
Complete promotion alone creates active frame-modality evidence and once-only
embedding usage. No model time/tokens are invented for the original OCR or copies.

Slice each frame's OCR at deterministic 1,200-code-point offsets without rewriting
code/whitespace; omit whitespace-only slices. Stable segment identity includes
source, generation, parser version, frame, offset and text digest. Actual decoded
PTS is a point (start=end), not proof of a duration. Preserve original extraction
and gallery provenance through processing-version/frame scoped foreign keys.

Saved answers/history inspect immutable evidence even after reindexing. Every
visual citation is labeled machine-generated, unreviewed OCR and links the retained
frame. Text-only models receive text/modality, not an implicit visual capability.
Complete deletion still removes segments, checkpoints, provenance, derived chat
and PNGs. No public MP4 API, new retention/format/provider, scene/quality approval,
assignment feature or paid fallback is authorized. See the visual-index plan.
