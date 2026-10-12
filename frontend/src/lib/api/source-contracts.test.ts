import { describe, expect, it } from "vitest";

import { isProcessing, parsePlaylistItems, parseSourceList } from "@/lib/api/source-contracts";

const source = {
  id: "12345678-1234-1234-1234-123456789abc", filename: "tutorial.vtt", status: "created",
  generation: 1, active_generation: null, segment_count: 0, provider: "upload", failure_code: null,
  job: { id: "12345678-1234-1234-1234-123456789abd", status: "pending", stage: "queued", progress_percent: 0, attempt_count: 0, max_attempts: 3, failure_code: null },
};

describe("source contracts", () => {
  it("validates a pending source and stops polling terminal jobs", () => {
    const parsed = parseSourceList({ items: [source] })[0];
    expect(isProcessing(parsed)).toBe(true);
    expect(isProcessing({ ...parsed, job: { ...parsed.job!, status: "succeeded" } })).toBe(false);
  });
  it("rejects invalid identifiers and progress values", () => {
    expect(() => parseSourceList({ items: [{ ...source, id: "../../other" }] })).toThrow();
    expect(() => parseSourceList({ items: [{ ...source, job: { ...source.job, progress_percent: 101 } }] })).toThrow();
  });
  it("validates ordered item identity, bounds and nullable transcript relationships", () => {
    const item = { id: source.id, playlist_source_id: source.job.id, generation: 1, position: 0,
      video_id: "abcdefghijk", title: "Lesson", transcript_source_id: null };
    expect(parsePlaylistItems({ playlist_items: [item] })[0]).toEqual(item);
    expect(parsePlaylistItems({ items: [] })).toEqual([]);
    for (const patch of [{ generation: 0 }, { position: -1 }, { video_id: "../../private" }, { transcript_source_id: "bad" }]) {
      expect(() => parsePlaylistItems({ playlist_items: [{ ...item, ...patch }] })).toThrow();
    }
    expect(() => parsePlaylistItems({ playlist_items: [item, item] })).toThrow();
  });
  it("preserves explicit truncation through the server-only inventory proxy", () => {
    const upstream = parseSourceList({ items: [{ ...source, kind: "youtube_playlist", metadata: { truncated: true } }] });
    expect(parseSourceList({ items: upstream })[0].playlist_truncated).toBe(true);
    expect(() => parseSourceList({ items: [{ ...source, playlist_truncated: "true" }] })).toThrow();
  });
  it('retains reindex state through the source proxy and rejects malformed flags', () => {
    const upstream = parseSourceList({items:[{...source,active_embedding_space:'signed-hash-v1:64',reindex_required:true}]});
    expect(parseSourceList({items:upstream})[0].reindex_required).toBe(true);
    expect(parseSourceList({items:upstream})[0].active_embedding_space).toBe('signed-hash-v1:64');
    expect(() => parseSourceList({items:[{...source,reindex_required:'true'}]})).toThrow();
  });
});
