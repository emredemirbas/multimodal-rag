import { describe, expect, it } from "vitest";
import { parseEvidence, parseTurn } from "@/lib/api/chat-contracts";
import { visualFixture } from "../../../test-support/visual-fixture";

const gallery = visualFixture();
const evidence = { segment_id: "55555555-5555-4555-8555-555555555555", source_id: gallery.source_id, source_filename: gallery.source_filename,
  start_ms: 0, end_ms: 0, modality: "frame", frame_id: gallery.items[0].id, visual_origin: gallery.origin,
  generation: 3, processing_version: "visual-ocr-chunks-v1:g3", text: gallery.items[0].ocr_text };

describe("versioned OCR evidence", () => {
  it("preserves point-zero timestamps, literal text and origin in evidence and persisted turns", () => {
    const parsed = parseEvidence({ ...evidence, object_key: "PRIVATE", input_sha256: "PRIVATE" });
    expect(parsed.start_ms).toBe(0); expect(parsed.end_ms).toBe(0);
    expect(parsed.text).toBe(evidence.text); expect(parsed.visual_origin).toEqual(gallery.origin);
    expect(parsed).not.toHaveProperty("object_key");
    const turn = parseTurn({ id: evidence.segment_id, sequence: 1, question: "user_id", source_ids: [], created_at: "2026-10-27T12:00:00Z",
      response: { answer: "Unreviewed OCR", abstained: false, citations: [evidence], provider: "local-deterministic", model: "extractive" } });
    expect(turn.response.citations[0].frame_id).toBe(evidence.frame_id);
  });
  it.each(["missing-frame", "transcript", "interval", "reviewed", "generation", "version", "timestamp", "profile"])("rejects %s mismatch", (kind) => {
    const row = structuredClone(evidence);
    if (kind === "missing-frame") Object.assign(row, { frame_id: null });
    if (kind === "transcript") row.modality = "transcript";
    if (kind === "interval") row.end_ms = 1;
    if (kind === "reviewed") Object.assign(row.visual_origin!, { human_reviewed: true });
    if (kind === "generation") row.generation = 1;
    if (kind === "version") row.processing_version = "transcript-chunks-v1:g3";
    if (kind === "timestamp") row.start_ms = row.end_ms = 600000;
    if (kind === "profile") row.visual_origin!.profile = "changed";
    expect(() => parseEvidence(row)).toThrow();
  });
});
