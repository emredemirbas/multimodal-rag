import { describe, expect, it, vi } from "vitest";
import { parseVisualGallery } from "@/lib/api/visual-contracts";
import { visualFixture, sourceId, projectId } from "../../../test-support/visual-fixture";
vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));
import { requestJson } from "@/lib/api/client";
import { getVisualGallery } from "@/lib/api/visuals";

describe("selected frame contracts", () => {
  it("preserves literal OCR and exact origin while stripping unknown keys", () => {
    expect(parseVisualGallery({ ...visualFixture(), object_key: "PRIVATE" })).toEqual(visualFixture());
  });
  it.each(["duplicate", "order", "dimensions", "profile", "reviewed", "searchable", "missing", "text"])("rejects %s corruption", (kind) => {
    const row = visualFixture();
    if (kind === "duplicate") row.items.push({ ...row.items[0], ordinal: 1, timestamp_ms: 10000, sample_target_ms: 10000 });
    if (kind === "order") row.items[0].ordinal = 1;
    if (kind === "dimensions") row.items[0].width = 961;
    if (kind === "profile") row.origin!.profile = "private-path";
    if (kind === "reviewed") Object.assign(row.origin!, { human_reviewed: true });
    if (kind === "searchable") Object.assign(row, { searchable: true });
    if (kind === "missing") row.items = [];
    if (kind === "text") row.items[0].ocr_text = "x".repeat(16001);
    expect(() => parseVisualGallery(row)).toThrow();
  });
  it("accepts bounded non-BMP code points and honest empty state", () => {
    const row = visualFixture(); row.items[0].ocr_text = "😀".repeat(16000);
    expect(parseVisualGallery(row).items[0].ocr_text).toHaveLength(32000);
    expect(parseVisualGallery({ ...row, generation: null, processing_version: null, published_at: null, origin: null, items: [] }).items).toEqual([]);
  });
  it("rejects an upstream gallery from another source", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...visualFixture(), source_id: projectId });
    await expect(getVisualGallery(projectId, sourceId)).rejects.toMatchObject({ status: 502 });
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}/frames`);
  });
  it("keeps completed gallery and versioned index state separate", () => {
    const row = { ...visualFixture(), searchable: true, active_index_generation: 3, active_embedding_space: "signed-hash-v1:64" };
    expect(parseVisualGallery(row).active_index_generation).toBe(3);
    expect(() => parseVisualGallery({ ...row, active_index_generation: 2 })).toThrow();
    expect(() => parseVisualGallery({ ...row, active_embedding_space: null })).toThrow();
    expect(() => parseVisualGallery({ ...row, searchable: false })).toThrow();
  });
});
