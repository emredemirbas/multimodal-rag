import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VisualGallery } from "@/components/sources/visual-gallery";
import { visualFixture, projectId } from "../../../test-support/visual-fixture";

describe("selected-frame gallery", () => {
  it("shows indexed OCR without implying image understanding or original playback", () => {
    render(<VisualGallery projectId={projectId} gallery={{ ...visualFixture(), searchable: true, active_index_generation: 3, active_embedding_space: "signed-hash-v1:64" }} />);
    expect(screen.getByText(/OCR is indexed at generation 3/)).toHaveTextContent("matching embedding space");
    expect(screen.queryByText(/not indexed for questions/)).toBeNull();
    expect(screen.getByText(/Active OCR embedding space/)).toHaveTextContent("signed-hash-v1:64");
  });
  it("renders exact times, unreviewed processing origin and hostile OCR literally", () => {
    const gallery = visualFixture();
    render(<VisualGallery projectId={projectId} gallery={gallery} />);
    expect(screen.getByRole("heading", { name: "Frame 1 · 00:05" })).toBeVisible();
    expect(screen.getByText(/user_id/).textContent).toBe(gallery.items[0].ocr_text);
    expect(screen.getByRole("region", { name: "Automatic visual processing provenance" })).toHaveTextContent("Extraction generation 1 · gallery generation 2");
    expect(screen.getByText(/not indexed for questions or citations/)).toBeVisible();
    expect(document.querySelector("script,video,audio,iframe")).toBeNull();
    expect(screen.getByRole("img").getAttribute("src")).toContain(`/api/projects/${projectId}/frames/${gallery.items[0].id}/image`);
  });
  it("retains accessible OCR when an image fails and allows a new image request", async () => {
    render(<VisualGallery projectId={projectId} gallery={visualFixture()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading selected frame");
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert")).toHaveTextContent("OCR below remains available");
    expect(screen.getByText(/user_id/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry frame image" }));
    fireEvent.load(screen.getByRole("img"));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });
  it("shows honest empty-gallery and empty-OCR states", () => {
    const gallery = visualFixture(); gallery.items[0].ocr_text = "";
    const { rerender } = render(<VisualGallery projectId={projectId} gallery={gallery} />);
    expect(screen.getByText(/No OCR text was recognized/)).toBeVisible();
    rerender(<VisualGallery projectId={projectId} gallery={{ ...gallery, items: [], origin: null, generation: null, processing_version: null, published_at: null }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Incomplete processing results are not shown");
    expect(screen.queryByRole("img")).toBeNull();
  });
});
