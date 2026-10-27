import type { TimelineAlignment } from "../src/lib/api/alignment-contracts";
import { visualFixture } from "./visual-fixture";
export const transcriptId = "55555555-5555-4555-8555-555555555555";
export const spanId = "66666666-6666-4666-8666-666666666666";
export function alignmentFixture(): TimelineAlignment {
  const gallery = visualFixture();
  return { method: "retained-pts-in-transcript-spans-v1", relationship: "user_asserted", semantics_verified: false,
    offset_ms: 0, gallery, transcript: { source_id: transcriptId, source_filename: "owned.vtt", generation: 1,
      active_generation: 1, processing_version: "transcript-chunks-v1", asr_origin: null }, matched_frames: 1,
    items: [{ frame_id: gallery.items[0].id, transcript_time_ms: 5000, matches_truncated: false,
      matches: [{ segment_id: spanId, start_ms: 5000, end_ms: 8000,
        excerpt: '<script>not executable</script> user_id', text_truncated: false }] }] };
}
