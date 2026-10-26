import type { VisualGallery } from "../src/lib/api/visual-contracts";
export const projectId = "11111111-1111-4111-8111-111111111111";
export const sourceId = "22222222-2222-4222-8222-222222222222";
export function visualFixture(): VisualGallery {
  return { source_id: sourceId, source_filename: "owned.mp4", generation: 2, processing_version: "retained-frames-v1",
    published_at: "2026-10-26T12:00:00Z", searchable: false,
    origin: { machine_generated: true, human_reviewed: false, job_id: "33333333-3333-4333-8333-333333333333", generation: 1,
      profile: "local-visual-v1:" + "a".repeat(64), language: "tr", engines: { ffmpeg: "5.1.9", tesseract: "5.3.0" },
      checkpoint_version: "visual-checkpoint-v1", prepared_at: "2026-10-26T11:59:00Z" },
    items: [{ id: "44444444-4444-4444-8444-444444444444", ordinal: 0, timestamp_ms: 5000, sample_target_ms: 5000,
      width: 16, height: 16, ocr_text: '<script>alert("PRIVATE")</script>\nuser_id · sağlık' }] };
}
