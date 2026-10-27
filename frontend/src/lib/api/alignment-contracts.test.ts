import { describe, expect, it } from "vitest";
import { alignmentHref, parseAlignmentQuery, parseTimelineAlignment } from "@/lib/api/alignment-contracts";
import { alignmentFixture, transcriptId } from "../../../test-support/alignment-fixture";
import { projectId, sourceId } from "../../../test-support/visual-fixture";

describe("temporal alignment contracts", () => {
  it("requires an explicit source assertion and pins both generations", () => {
    expect(parseAlignmentQuery({})).toBeNull();
    const query = parseAlignmentQuery({ transcript_source_id: transcriptId, assert_same_recording: "true", offset_ms: "-2000",
      visual_generation: "2", transcript_generation: "1" })!;
    expect(query.offset_ms).toBe(-2000);
    expect(alignmentHref(projectId, sourceId, query)).toContain("visual_generation=2&transcript_generation=1");
    expect(parseAlignmentQuery({ transcript_source_id: transcriptId, assert_same_recording: "true" })?.offset_ms).toBe(0);
    for (const patch of [{ assert_same_recording: "false" }, { assert_same_recording: undefined }, { offset_ms: "1.5" },
      { offset_ms: "1e3" }, { offset_ms: "-0" }, { offset_ms: "600001" }, { offset_ms: ["0", "1"] },
      { visual_generation: "2" }, { transcript_generation: "1" }, { visual_generation: "01", transcript_generation: "1" },
      { extra: "PRIVATE_QUERY" }, { transcript_source_id: "../foreign" }]) {
      expect(() => parseAlignmentQuery({ transcript_source_id: transcriptId, assert_same_recording: "true", ...patch })).toThrow();
    }
  });
  it("keeps literal content and immutable processing/point bindings", () => {
    const original = alignmentFixture(), parsed = parseTimelineAlignment(original);
    expect(parsed).toEqual(original);
    expect(parsed.items[0].matches[0].excerpt).toContain("<script>not executable</script>");
    expect(parsed.semantics_verified).toBe(false);
  });
  it.each(["verified", "source", "frame", "time", "boundary", "duplicates", "count", "order", "truncation", "excerpt", "generation"])("rejects invalid %s responses", (kind) => {
    const value = alignmentFixture();
    const item = value.items[0], span = item.matches[0];
    if (kind === "verified") Object.assign(value, { semantics_verified: true });
    if (kind === "source") value.transcript.source_id = sourceId;
    if (kind === "frame") item.frame_id = projectId;
    if (kind === "time") item.transcript_time_ms += 1;
    if (kind === "boundary") span.end_ms = 5000;
    if (kind === "duplicates") item.matches.push({ ...span });
    if (kind === "count") value.matched_frames = 0;
    if (kind === "order") item.matches.push({ ...span, start_ms: 4000, segment_id: projectId });
    if (kind === "truncation") item.matches_truncated = true;
    if (kind === "excerpt") { span.excerpt = "😀".repeat(4001); }
    if (kind === "generation") value.transcript.generation = 2;
    expect(() => parseTimelineAlignment(value)).toThrow();
  });
  it("handles gaps, negative points and bounded Unicode excerpts without perfect-match claims", () => {
    const value = alignmentFixture();
    value.offset_ms = -6000; value.items[0].transcript_time_ms = -1000;
    value.items[0].matches = []; value.matched_frames = 0;
    expect(parseTimelineAlignment(value).items[0].matches).toEqual([]);
    const long = alignmentFixture();
    long.items[0].matches[0].excerpt = "😀".repeat(4000);
    long.items[0].matches[0].text_truncated = true;
    expect(parseTimelineAlignment(long).matched_frames).toBe(1);
  });
});
