import { describe, expect, it } from "vitest";

import { validateProjectTitle } from "@/lib/validation/projects";

describe("project title validation", () => {
  it("trims a valid title", () => {
    expect(validateProjectTitle("  FastAPI fundamentals  ")).toEqual({
      ok: true,
      title: "FastAPI fundamentals",
    });
  });

  it("rejects blank and oversized titles", () => {
    expect(validateProjectTitle("   ")).toEqual({
      ok: false,
      message: "Enter a project name.",
    });
    expect(validateProjectTitle("x".repeat(121))).toEqual({
      ok: false,
      message: "Project names must be 120 characters or fewer.",
    });
  });
});
