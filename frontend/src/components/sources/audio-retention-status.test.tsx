import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AudioRetentionStatus } from "@/components/sources/audio-retention-status";
import { retryCleanupAction } from "@/app/actions/sources";
import { audioRetention } from "../../../test-support/media-fixture";
import { projectId } from "../../../test-support/transcript-fixture";

vi.mock("@/app/actions/sources", () => ({ retryCleanupAction: vi.fn() }));

describe("original audio retention", () => {
  beforeEach(() => vi.mocked(retryCleanupAction).mockReset());
  it("has honest accessible expiry, pending, failure and confirmed-deletion states", () => {
    const refresh = vi.fn();
    const { rerender } = render(<AudioRetentionStatus projectId={projectId} retention={audioRetention()} onRefresh={refresh} />);
    expect(screen.getByRole("region", { name: "Original audio retention" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("temporary and eligible");
    expect(screen.getByText(/Scheduler or storage outages/)).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<AudioRetentionStatus projectId={projectId} retention={audioRetention("expired")} onRefresh={refresh} />);
    expect(screen.getByRole("status")).toHaveTextContent("Physical deletion is not confirmed");
    rerender(<AudioRetentionStatus projectId={projectId} retention={audioRetention("cleanup_pending")} onRefresh={refresh} />);
    expect(screen.getByRole("status")).toHaveTextContent("Physical deletion is pending");
    rerender(<AudioRetentionStatus projectId={projectId} retention={audioRetention("cleanup_failed")} onRefresh={refresh} />);
    expect(screen.getByRole("button", { name: "Retry original audio cleanup" })).toBeVisible();
    expect(screen.getByRole("status")).not.toHaveTextContent("deletion confirmed");
    rerender(<AudioRetentionStatus projectId={projectId} retention={audioRetention("deleted")} onRefresh={refresh} />);
    expect(screen.getByRole("status")).toHaveTextContent("Original audio deletion confirmed");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/derived transcript, if created, is retained/)).toBeVisible();
  });
  it("refreshes after an authorized retry without inventing physical deletion", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const retention = audioRetention("cleanup_failed");
    vi.mocked(retryCleanupAction).mockResolvedValue({ status: "success", version: 1, message: "File cleanup retry accepted." });
    render(<AudioRetentionStatus projectId={projectId} retention={retention} onRefresh={refresh} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Retry original audio cleanup" })); });
    expect(retryCleanupAction).toHaveBeenCalledTimes(1);
    const form = vi.mocked(retryCleanupAction).mock.calls[0][1];
    expect(form.get("projectId")).toBe(projectId);
    expect(form.get("cleanupId")).toBe(retention.cleanup_id);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("deletion is not confirmed");
  });
  it("announces retry failure while leaving the receipt visibly failed", async () => {
    const refresh = vi.fn();
    vi.mocked(retryCleanupAction).mockResolvedValue({ status: "error", version: 1, message: "Cleanup could not be retried. Try again shortly." });
    render(<AudioRetentionStatus projectId={projectId} retention={audioRetention("cleanup_failed")} onRefresh={refresh} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Retry original audio cleanup" })); });
    expect(screen.getByRole("alert")).toHaveTextContent("could not be retried");
    expect(screen.getByRole("status")).toHaveTextContent("Original audio cleanup failed");
    expect(refresh).not.toHaveBeenCalled();
  });
});
