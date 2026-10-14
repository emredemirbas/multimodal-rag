export const projectId = "12345678-1234-1234-1234-123456789abc";
export const sourceId = "22345678-1234-1234-1234-123456789abc";
export function transcriptFixture(page = 1) {
  return { source_id: sourceId, source_filename: "tutorial.vtt", source_kind: "transcript", source_status: "ready",
    generation: 1, active_generation: 1, processing_version: "transcript-v2:g1", page, page_size: 50, total_segments: 53, total_pages: 2,
    items: Array.from({ length: page === 1 ? 50 : 3 }, (_, index) => {
      const ordinal = (page - 1) * 50 + index;
      return { segment_id: `32345678-1234-1234-1234-${ordinal.toString(16).padStart(12, "0")}`,
        source_id: sourceId, source_filename: "tutorial.vtt", generation: 1, processing_version: "transcript-v2:g1",
        start_ms: ordinal * 10_000 + 1250, end_ms: ordinal * 10_000 + 5500, text: `Segment ${ordinal}. GET /health.`, modality: "transcript" };
    }) };
}
