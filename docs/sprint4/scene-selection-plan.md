# Isolated change-aware candidate prototype

Date: 2026-10-27. Scope: first scene/change-selection component of Sprint 4,
not an application sampling/profile change or an additional model/retention class.
Status: Prototype implemented and locally verified; see `scene-selection-validation.md`.

## Assumptions and boundary

Existing uniform sampling can miss a transient view. Test a deterministic bounded
alternative before changing immutable managed visual profiles. A separate explicit
operator CLI reuses the accepted MP4 validator/native runner/kernel restrictions;
it never creates a source, queue job, PNG object, OCR text or application record.
Existing `VisualIdentity`/`WireResult`, checkpoint digests, galleries, old citations,
native service and upload defaults remain byte-compatible and unchanged.

- Scan actual source frames at least one second apart, retaining original decoded
  PTS, not synthesized FPS timestamps. At most 600 grayscale <=160x90 thumbnails;
  video <=100 MB / 600s and existing codec/timeline restrictions. Validate count,
  geometry, source-FPS-bounded gaps and coverage through the end; reject truncated
  output instead of treating a partial scan as complete. Existing child CPU/wall/
  file bounds still apply and may reject complex inputs.
- Compare adjacent thumbnails. Count pixels differing by >=24 gray levels and
  record absolute-difference magnitude. Changes covering >=0.2% of pixels are
  eligible. These are experimental noise/ranking parameters, **not reviewed
  quality thresholds**. Downscaling/one-second scanning can miss brief/small code
  changes; cursor motion, fades or noise may consume the budget.
- Keep up to four timeline anchors (nearest actual sample, earlier tie), then
  highest-ranked eligible changes within the existing 20-point final budget.
  Rank deterministically by changed-pixel fraction, mean absolute difference and
  earlier PTS. Keep temporal returns even if pixels match an earlier view; never
  invent a frame's visible duration. No blanket perceptual deduplication of code.
- Version the standalone policy/engine/profile and report actual selected PTS,
  bounded counts/scores/hashes only. No pixels, OCR, paths or raw native errors.
  Require operator rights acknowledgement before stdin; no automatic download,
  paid provider, host data mount or new output exporter.

The filter uses `select` and `prev_selected_t`, whose timestamp/minimum-distance
semantics are documented in the pinned [official FFmpeg source docs](https://github.com/FFmpeg/FFmpeg/blob/n5.1.9/doc/filters.texi#L26218-L26348).
The thumbnail/ranking/budget choices are application experiments, not FFmpeg
quality guarantees. Keep fixed demuxer/protocol/external-reference restrictions.

## Verification and next gate

Test arithmetic, timeline/geometry/count bounds, deterministic ties/budget,
static input/noise, transient/return views, actual versus requested PTS, malformed
input and safe CLI/native failures. Use an authored 20-second video with a brief
view at 3–4s, between the existing five-second sample points: compare the **actual**
old pipeline and new scan in separate no-network native runs. This tiny synthetic
comparison is not representative scene/code recall or a quality threshold.

Application integration is a later gate: explicitly version policy/protocol and
persist/revalidate its candidate manifest, preserve legacy digests/history, add
migration if storage changes, test auth/retry/deletion and update truthful UI.
Do not bypass those requirements by relabeling new selections as the old uniform
policy. Keep this delivery small and make its remaining boundary visible.
