import { describe, expect, it } from "vitest";
import { parseTranscriptPage, parseTranscriptQuery, transcriptHref } from "@/lib/api/transcript-contracts";
import { projectId, sourceId, transcriptFixture } from "../../../test-support/transcript-fixture";

describe("published transcript contract", () => {
  it("validates bounded pages, empty and older-generation evidence", () => {
    expect(parseTranscriptPage(transcriptFixture()).items).toHaveLength(50);
    expect(parseTranscriptPage({ ...transcriptFixture(2), active_generation: 2 }).generation).toBe(1);
    expect(parseTranscriptPage({ ...transcriptFixture(), generation: null, active_generation: null,
      processing_version: null, total_segments: 0, total_pages: 0, items: [] }).items).toEqual([]);
    expect(parseTranscriptPage({ ...transcriptFixture(), total_segments: 10_001, total_pages: 201 }).total_pages).toBe(201);
  });
  it("rejects malformed pagination, unknown generations and inconsistent counts", () => {
    for (const change of [{ page: 0 }, { page: 3 }, { total_segments: 100_001 }, { page_size: 500 }, { total_pages: 3 },
      { generation: 2 }, { generation: null }, { processing_version: null }, { items: [] }, { active_generation: 0 }, { source_id: "bad" }]) {
      expect(() => parseTranscriptPage({ ...transcriptFixture(), ...change })).toThrow();
    }
  });
  it("rejects mixed source/generation/version/modality and duplicate or unsorted evidence", () => {
    const fixture = transcriptFixture();
    for (const change of [{ source_id: projectId }, { source_filename: "foreign.vtt" }, { generation: 2 },
      { processing_version: "different" }, { modality: "frame" }, { text: "x".repeat(2_000_001) }]) {
      expect(() => parseTranscriptPage({ ...fixture, items: [{ ...fixture.items[0], ...change }, ...fixture.items.slice(1)] })).toThrow();
    }
    expect(() => parseTranscriptPage({ ...fixture, items: [fixture.items[0], fixture.items[0], ...fixture.items.slice(2)] })).toThrow();
    expect(() => parseTranscriptPage({ ...fixture, items: [...fixture.items].reverse() })).toThrow();
  });
  it("requires explicit bounded generation on subsequent pages and retains it in URLs", () => {
    expect(parseTranscriptQuery({})).toEqual({ generation: undefined, page: 1 });
    expect(parseTranscriptQuery({ generation: "2", page: "2" })).toEqual({ generation: 2, page: 2 });
    for (const query of [{ page: "2" }, { page: "0" }, { page: "2001" }, { generation: "0" }, { generation: "2147483648" },
      { generation: ["1", "2"] }, { generation: " 1" }, { page: "1.5" }, { page: "01" }, { generation: "<script>" }]) {
      expect(() => parseTranscriptQuery(query)).toThrow();
    }
    expect(transcriptHref(projectId, sourceId, 2, 2)).toBe(`/projects/${projectId}/sources/${sourceId}/transcript?generation=2&page=2`);
  });
});
