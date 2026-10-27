import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlignmentForm, AlignmentViewer } from "@/components/sources/timeline-alignment";
import type { SourceItem } from "@/lib/api/source-contracts";
import { alignmentFixture, spanId, transcriptId } from "../../../test-support/alignment-fixture";
import { projectId, sourceId } from "../../../test-support/visual-fixture";
const textSource: SourceItem = { id: transcriptId, filename: "owned.vtt", kind: "transcript", status: "ready", generation: 1,
  active_generation: 1, segment_count: 2, provider: "upload", job: null, failure_code: null };
describe("frame and transcript timeline", () => {
  it("requires an explicit pairing, offers only published text sources and explains signed offsets", () => {
    render(<AlignmentForm projectId={projectId} sourceId={sourceId} sources={[textSource,
      { ...textSource, id: projectId, active_generation: null, filename: "pending.vtt" },
      { ...textSource, id: sourceId, kind: "video", filename: "owned.mp4" }]} />);
    expect(screen.getByRole("option", { name: "owned.vtt" })).toBeVisible();
    expect(screen.queryByRole("option", { name: "owned.mp4" })).toBeNull();
    expect(screen.queryByRole("option", { name: "pending.vtt" })).toBeNull();
    expect(screen.getByRole("checkbox")).toBeRequired();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByLabelText("Transcript offset (milliseconds)")).toHaveAttribute("step", "1");
    expect(screen.getByText(/Transcript time = frame time/)).toHaveTextContent("+2000");
    expect(document.querySelector("form")).toHaveAttribute("method", "get");
    expect(document.querySelector("form")).toHaveAttribute("action", `/projects/${projectId}/sources/${sourceId}/frames/align`);
  });
  it("shows an actionable no-transcript state", () => {
    render(<AlignmentForm projectId={projectId} sourceId={sourceId} sources={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("No published transcript available");
    expect(screen.queryByRole("button", { name: "Compare published evidence" })).toBeNull();
  });
  it("renders literal side-by-side evidence, precise times and distinct unverified origins", () => {
    const view = alignmentFixture();
    render(<AlignmentViewer projectId={projectId} view={view} />);
    expect(screen.getByRole("note")).toHaveTextContent("not verified audiovisual identity");
    expect(screen.getByText(/1 of 1 frames overlap/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Transcript at 00:05" })).toBeVisible();
    expect(screen.getByText(view.items[0].matches[0].excerpt)).toBeVisible();
    expect(document.querySelector("script,iframe,video,audio")).toBeNull();
    expect(screen.getByRole("link", { name: /Inspect transcript evidence/ })).toHaveAttribute("href", `/projects/${projectId}/evidence/${spanId}`);
    expect(screen.getByRole("link", { name: "Browse this transcript generation" })).toHaveAttribute("href", `/projects/${projectId}/sources/${transcriptId}/transcript?generation=1&page=1`);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert")).toHaveTextContent("OCR below remains available");
    expect(screen.getByText(view.items[0].matches[0].excerpt)).toBeVisible();
  });
  it("does not fill gaps, hides no truncation and labels an older transcript generation", () => {
    const view = alignmentFixture();
    view.transcript.active_generation = 2;
    view.offset_ms = -6000; view.items[0].transcript_time_ms = -1000;
    view.items[0].matches = []; view.matched_frames = 0;
    const { rerender } = render(<AlignmentViewer projectId={projectId} view={view} />);
    expect(screen.getByRole("heading", { name: "Transcript at −00:01" })).toBeVisible();
    expect(screen.getByText(/No transcript span contains/)).toHaveTextContent("No text was inferred");
    expect(screen.getByText(/older published generation/)).toBeVisible();
    const long = alignmentFixture(); long.items[0].matches[0].text_truncated = true; long.items[0].matches_truncated = true;
    rerender(<AlignmentViewer projectId={projectId} view={long} />);
    expect(screen.getByText(/Excerpt shortened/)).toBeVisible();
    expect(screen.getByText(/Showing the first 5 overlapping spans/)).toBeVisible();
  });
});
