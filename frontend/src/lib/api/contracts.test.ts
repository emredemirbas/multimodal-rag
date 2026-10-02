import { describe, expect, it } from "vitest";

import { parseProject, parseProjectList } from "@/lib/api/contracts";

const PROJECT = {
  id: "e6071280-749a-4aa1-8156-d525789c6a8f",
  tenant_id: "tenant-a",
  title: "FastAPI fundamentals",
  status: "active",
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
  archived_at: null,
};

describe("project API contracts", () => {
  it("accepts the documented project-list shape", () => {
    expect(parseProjectList({ items: [PROJECT] })).toEqual({ items: [PROJECT] });
  });

  it("rejects an unknown project status", () => {
    expect(() => parseProject({ ...PROJECT, status: "deleted" })).toThrow(/API contract/);
  });
});
