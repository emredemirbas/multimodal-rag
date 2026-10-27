import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvidencePage from "@/app/projects/[projectId]/evidence/[segmentId]/page";
import { requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { asrOrigin } from "../../../../../../test-support/media-fixture";
import { projectId, transcriptFixture } from "../../../../../../test-support/transcript-fixture";
import { visualFixture } from "../../../../../../test-support/visual-fixture";

vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); } }));
const evidence = { ...transcriptFixture().items[0], generation: 2, asr_origin: asrOrigin };
function page(segment = evidence.segment_id) { return EvidencePage({ params: Promise.resolve({ projectId, segmentId: segment }) }); }

describe("machine-generated evidence inspection", () => {
  beforeEach(() => { vi.mocked(requestJson).mockReset(); });
  it("links point-in-time unreviewed OCR to the exact supporting frame without a fake player", async () => {
    const gallery = visualFixture();
    vi.mocked(requestJson).mockResolvedValue({ ...evidence, asr_origin: null, visual_origin: gallery.origin, frame_id: gallery.items[0].id,
      modality: "frame", generation: 3, processing_version: "visual-ocr-chunks-v1:g3", start_ms: 0, end_ms: 0, text: gallery.items[0].ocr_text });
    render(await page());
    expect(screen.getByRole("region", { name: "Visual evidence provenance" })).toHaveTextContent("not human-reviewed");
    expect(screen.getByText(/00:00 \(actual frame timestamp\)/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Inspect the supporting frame and full OCR" })).toHaveAttribute("href", `/projects/${projectId}/sources/${evidence.source_id}/frames#frame-${gallery.items[0].id}`);
    expect(screen.queryByRole("link", { name: "Read this transcript generation" })).toBeNull();
    expect(screen.getByText(/No original-video player/)).toBeVisible();
    expect(document.querySelector("script,video,audio,iframe")).toBeNull();
  });
  it("shows version-pinned provenance, correction guidance and literal untrusted text", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...evidence, text: '<img src=x onerror="alert(1)"> GET /health' });
    render(await page());
    expect(screen.getByRole("region", { name: "Automatic transcription provenance" })).toHaveTextContent("not human-reviewed");
    expect(screen.getByText(/Speech, code identifiers and timestamps may be wrong/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Read this transcript generation" })).toHaveAttribute("href", `/projects/${projectId}/sources/${evidence.source_id}/transcript?generation=2&page=1`);
    expect(screen.getByText(/<img src=x/)).toBeVisible();
    expect(document.querySelector("img,script,audio,video,iframe")).toBeNull();
  });
  it("does not infer human review or machine origin for legacy evidence", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...evidence, asr_origin: null });
    render(await page());
    expect(screen.queryByRole("region", { name: "Automatic transcription provenance" })).not.toBeInTheDocument();
    expect(screen.getByText(evidence.text)).toBeVisible();
  });
  it("uses not-found/safe retry states instead of displaying invalid provenance", async () => {
    await expect(page("bad-id")).rejects.toThrow("not-found");
    expect(requestJson).not.toHaveBeenCalled();
    vi.mocked(requestJson).mockRejectedValueOnce(new ApiError({ status: 404, code: "not_found" }));
    await expect(page()).rejects.toThrow("not-found");
    vi.mocked(requestJson).mockResolvedValue({ ...evidence, asr_origin: { ...asrOrigin, requested_language: ["en"] } });
    render(await page());
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.getByRole("link", { name: "Retry" })).toHaveAttribute("href", `/projects/${projectId}/evidence/${evidence.segment_id}`);
    expect(screen.queryByRole("region", { name: "Automatic transcription provenance" })).not.toBeInTheDocument();
  });
});
