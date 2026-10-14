import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TranscriptPage from "@/app/projects/[projectId]/sources/[sourceId]/transcript/page";
import { ApiError } from "@/lib/api/errors";
import { getTranscript } from "@/lib/api/transcripts";
import { projectId, sourceId, transcriptFixture } from "../../../../../../../test-support/transcript-fixture";

vi.mock("@/lib/api/transcripts", () => ({ getTranscript: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); } }));

describe("transcript route", () => {
  beforeEach(() => { vi.mocked(getTranscript).mockReset(); });
  function page(query: { generation?: string | string[]; page?: string | string[] } = {}, source = sourceId) {
    return TranscriptPage({ params: Promise.resolve({ projectId, sourceId: source }), searchParams: Promise.resolve(query) });
  }
  it("passes a pinned query to the server-only reader", async () => {
    vi.mocked(getTranscript).mockResolvedValue(transcriptFixture(2));
    render(await page({ generation: "1", page: "2" }));
    expect(getTranscript).toHaveBeenCalledWith(projectId, sourceId, { generation: 1, page: 2 });
    expect(screen.getByRole("heading", { name: "tutorial.vtt" })).toBeVisible();
  });
  it("rejects invalid route/query and unknown scopes without provider access", async () => {
    await expect(page({ page: "2" })).rejects.toThrow("not-found");
    await expect(page({ generation: ["1", "2"] })).rejects.toThrow("not-found");
    await expect(page({}, "invalid")).rejects.toThrow("not-found");
    expect(getTranscript).not.toHaveBeenCalled();
    vi.mocked(getTranscript).mockRejectedValue(new ApiError({ status: 404, code: "not_found" }));
    await expect(page()).rejects.toThrow("not-found");
  });
  it("shows safe failure and retains the exact retry version/page", async () => {
    vi.mocked(getTranscript).mockRejectedValue(new ApiError({ status: 503, code: "upstream_unavailable", message: "private detail" }));
    render(await page({ generation: "1", page: "2" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Transcript could not load");
    expect(screen.getByRole("link", { name: "Retry" })).toHaveAttribute("href", `/projects/${projectId}/sources/${sourceId}/transcript?generation=1&page=2`);
    expect(screen.queryByText("private detail")).not.toBeInTheDocument();
  });
});
