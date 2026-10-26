import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FramesPage from "@/app/projects/[projectId]/sources/[sourceId]/frames/page";
import { ApiError } from "@/lib/api/errors";
import { getVisualGallery } from "@/lib/api/visuals";
import { visualFixture, projectId, sourceId } from "../../../../../../../test-support/visual-fixture";
vi.mock("@/lib/api/visuals", () => ({ getVisualGallery: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); } }));
describe("selected frame page", () => {
  beforeEach(() => { vi.mocked(getVisualGallery).mockReset(); });
  function page(source = sourceId) { return FramesPage({ params: Promise.resolve({ projectId, sourceId: source }) }); }
  it("reads a scoped gallery and renders the retained view", async () => {
    vi.mocked(getVisualGallery).mockResolvedValue(visualFixture());
    render(await page());
    expect(getVisualGallery).toHaveBeenCalledWith(projectId, sourceId);
    expect(screen.getByRole("heading", { name: "Selected frames · owned.mp4" })).toBeVisible();
  });
  it("rejects invalid and missing sources without exposing an upstream detail", async () => {
    await expect(page("../foreign")).rejects.toThrow("not-found");
    expect(getVisualGallery).not.toHaveBeenCalled();
    vi.mocked(getVisualGallery).mockRejectedValue(new ApiError({ status: 404 }));
    await expect(page()).rejects.toThrow("not-found");
  });
  it("renders safe errors with a scoped retry", async () => {
    vi.mocked(getVisualGallery).mockRejectedValue(new ApiError({ status: 503, message: "PRIVATE_UPSTREAM" }));
    render(await page());
    expect(screen.getByRole("alert")).toHaveTextContent("Selected frames could not load");
    expect(screen.getByRole("link", { name: "Retry" })).toHaveAttribute("href", `/projects/${projectId}/sources/${sourceId}/frames`);
    expect(screen.queryByText("PRIVATE_UPSTREAM")).toBeNull();
  });
});
