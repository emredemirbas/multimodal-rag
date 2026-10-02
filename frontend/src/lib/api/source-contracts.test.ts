import { describe, expect, it } from "vitest";

import { isProcessing, parseSourceList } from "@/lib/api/source-contracts";

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
});
