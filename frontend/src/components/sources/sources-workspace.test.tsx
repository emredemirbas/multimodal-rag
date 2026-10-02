import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesWorkspace } from "@/components/sources/sources-workspace";
import type { SourceItem } from "@/lib/api/source-contracts";

vi.mock("@/app/actions/sources", () => ({ uploadSourceAction: vi.fn(), metadataSourceAction: vi.fn(), sourceCommandAction: vi.fn(), retryCleanupAction: vi.fn() }));
const projectId = "12345678-1234-1234-1234-123456789abc";
const source: SourceItem = {
  id: "12345678-1234-1234-1234-123456789abd", filename: "tutorial.vtt", status: "ready", generation: 1,
  active_generation: 1, segment_count: 3, provider: "upload", failure_code: null,
  job: { id: "12345678-1234-1234-1234-123456789abe", status: "succeeded", stage: "ready", progress_percent: 100, attempt_count: 1, max_attempts: 3, failure_code: null },
};

describe("source management", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [source] }) }));
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; };
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("has labelled bounded upload, explicit rights, empty and unavailable-media states", () => {
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    expect(screen.getByLabelText("SRT / VTT transcript")).toBeRequired();
    expect(screen.getAllByLabelText("Ownership / permission")[0]).toBeRequired();
    expect(screen.getByRole("heading", { name: "No sources yet" })).toBeVisible();
    expect(screen.getByText(/Audio\/video uploads are not yet available/)).toBeVisible();
    const file = new File(["x".repeat(2_000_001)], "too-large.vtt", { type: "text/vtt" });
    fireEvent.change(screen.getByLabelText("SRT / VTT transcript"), { target: { files: [file] } });
    expect(screen.getByRole("alert")).toHaveTextContent("at most 2 MB");
    expect(screen.getByRole("button", { name: "Process transcript" })).toBeDisabled();
  });

  it("shows progress and polls only active visible jobs, stopping when ready", async () => {
    const pending = { ...source, status: "processing", job: { ...source.job!, status: "running" as const, stage: "embedding", progress_percent: 50 } };
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "50");
    expect(screen.getByRole("button", { name: "Cancel processing" })).toBeVisible();
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { vi.advanceTimersByTime(10_000); });
    expect(fetch).not.toHaveBeenCalled();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await act(async () => { fireEvent(document, new Event("visibilitychange")); });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/No processing is currently running/)).toBeVisible();
    await act(async () => { vi.advanceTimersByTime(20_000); });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("confirms the named source and exposes recovery without polling terminal failures", () => {
    const failed = { ...source, status: "failed", generation: 2, job: { ...source.job!, status: "failed" as const, failure_code: "invalid_transcript" } };
    render(<SourcesWorkspace projectId={projectId} initialSources={[failed]} archived={true} />);
    expect(screen.queryByLabelText("SRT / VTT transcript")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry processing" })).toBeVisible();
    expect(screen.getByText(/Previously indexed generation 1 remains available/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));
    expect(screen.getByRole("dialog", { name: "Delete “tutorial.vtt”?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Keep source" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
