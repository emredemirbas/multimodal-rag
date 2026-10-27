import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AlignmentPage from "@/app/projects/[projectId]/sources/[sourceId]/frames/align/page";
import { getAlignment } from "@/lib/api/alignment";
import { listSources } from "@/lib/api/sources";
import { getVisualGallery } from "@/lib/api/visuals";
import { ApiError } from "@/lib/api/errors";
import { alignmentFixture, transcriptId } from "../../../../../../../../test-support/alignment-fixture";
import { projectId, sourceId, visualFixture } from "../../../../../../../../test-support/visual-fixture";
vi.mock("@/lib/api/alignment", () => ({ getAlignment: vi.fn() }));
vi.mock("@/lib/api/sources", () => ({ listSources: vi.fn() }));
vi.mock("@/lib/api/visuals", () => ({ getVisualGallery: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); }, redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));
const query = { transcript_source_id: transcriptId, assert_same_recording: "true", offset_ms: "0" };
function page(searchParams: Record<string, string | string[]> = {}, source = sourceId) {
  return AlignmentPage({ params: Promise.resolve({ projectId, sourceId: source }), searchParams: Promise.resolve(searchParams) });
}
describe("alignment page", () => {
  beforeEach(() => { vi.mocked(getAlignment).mockReset(); vi.mocked(getVisualGallery).mockReset(); vi.mocked(listSources).mockReset(); });
  it("opens a scoped selection page without inferring a relationship or calling alignment", async () => {
    vi.mocked(getVisualGallery).mockResolvedValue(visualFixture()); vi.mocked(listSources).mockResolvedValue([]);
    render(await page());
    expect(getVisualGallery).toHaveBeenCalledWith(projectId, sourceId);
    expect(listSources).toHaveBeenCalledWith(projectId);
    expect(getAlignment).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("No published transcript available");
  });
  it("pins both accepted generations before rendering the result", async () => {
    vi.mocked(getAlignment).mockResolvedValue(alignmentFixture());
    await expect(page(query)).rejects.toThrow("visual_generation=2&transcript_generation=1");
    render(await page({ ...query, visual_generation: "2", transcript_generation: "1" }));
    expect(screen.getByRole("heading", { name: "Frame and transcript timeline" })).toBeVisible();
    expect(listSources).not.toHaveBeenCalled();
  });
  it("rejects invalid ids, duplicate parameters and absent assertions before reads", async () => {
    await expect(page({}, "../foreign")).rejects.toThrow("not-found");
    await expect(page({ transcript_source_id: transcriptId })).rejects.toThrow("not-found");
    await expect(page({ ...query, offset_ms: ["0", "1"] })).rejects.toThrow("not-found");
    expect(getAlignment).not.toHaveBeenCalled(); expect(getVisualGallery).not.toHaveBeenCalled();
  });
  it("renders safe retry errors and hides missing scope", async () => {
    vi.mocked(getAlignment).mockRejectedValue(new ApiError({ status: 503, message: "PRIVATE_UPSTREAM" }));
    render(await page(query));
    expect(screen.getByRole("alert")).toHaveTextContent("Timeline comparison could not load");
    expect(screen.getByRole("link", { name: "Retry" }).getAttribute("href")).toContain(`transcript_source_id=${transcriptId}`);
    expect(screen.queryByText("PRIVATE_UPSTREAM")).toBeNull();
    vi.mocked(getAlignment).mockRejectedValue(new ApiError({ status: 404 }));
    await expect(page(query)).rejects.toThrow("not-found");
  });
  it("shows a useful incomplete-gallery state without rendering private frames", async () => {
    vi.mocked(getVisualGallery).mockResolvedValue({ ...visualFixture(), origin: null, items: [] }); vi.mocked(listSources).mockResolvedValue([]);
    render(await page());
    expect(screen.getByRole("status")).toHaveTextContent("No complete gallery yet");
    expect(screen.queryByRole("img")).toBeNull();
  });
});
