import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesWorkspace } from "@/components/sources/sources-workspace";
import { metadataSourceAction, sourceCommandAction, uploadSourceAction } from "@/app/actions/sources";
import type { PlaylistItem, SourceItem } from "@/lib/api/source-contracts";
import { asrOrigin, audioRetention } from "../../../test-support/media-fixture";

vi.mock("@/app/actions/sources", () => ({ uploadSourceAction: vi.fn(), metadataSourceAction: vi.fn(), sourceCommandAction: vi.fn(), retryCleanupAction: vi.fn() }));
const projectId = "12345678-1234-1234-1234-123456789abc";
const source: SourceItem = {
  id: "12345678-1234-1234-1234-123456789abd", filename: "tutorial.vtt", status: "ready", generation: 1,
  active_generation: 1, segment_count: 3, provider: "upload", failure_code: null,
  job: { id: "12345678-1234-1234-1234-123456789abe", status: "succeeded", stage: "ready", progress_percent: 100, attempt_count: 1, max_attempts: 3, failure_code: null },
};

describe("source management", () => {
  it("removes a confirmed deleted source and emits its ID even if the follow-up inventory fails", async () => {
    const onSourceDeleted = vi.fn();
    vi.mocked(sourceCommandAction).mockResolvedValueOnce({ status: "success", message: "Source removed.", version: 1,
      cleanup: { id: "32345678-1234-1234-1234-123456789abc", project_id: projectId, status: "pending" } });
    vi.mocked(fetch).mockRejectedValueOnce(new Error("refresh unavailable"));
    render(<SourcesWorkspace projectId={projectId} initialSources={[source]} archived={false} onSourceDeleted={onSourceDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Yes, delete source" })); });

    expect(onSourceDeleted).toHaveBeenCalledExactlyOnceWith(source.id);
    expect(screen.queryByRole("listitem", { name: source.filename })).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Sources could not refresh");
    expect(screen.getByText("Records removed; retained file cleanup is in progress.")).toBeVisible();
  });

  it.each(["error", "foreign-project"])("keeps the source and emits no deletion for a %s receipt", async (failure) => {
    const onSourceDeleted = vi.fn();
    vi.mocked(sourceCommandAction).mockResolvedValueOnce(failure === "error"
      ? { status: "error", message: "Deletion failed.", version: 1 }
      : { status: "success", message: "Source removed.", version: 1,
        cleanup: { id: "32345678-1234-1234-1234-123456789abc", project_id: "22345678-1234-1234-1234-123456789abc", status: "pending" } });
    render(<SourcesWorkspace projectId={projectId} initialSources={[source]} archived={false} onSourceDeleted={onSourceDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Yes, delete source" })); });

    expect(onSourceDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("listitem", { name: source.filename })).toBeVisible();
    expect(screen.getByRole("alert")).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not resurrect a deleted source when a pre-deletion inventory response arrives late", async () => {
    let resolveInventory!: (response: Response) => void;
    const onSourcesChanged = vi.fn(), onSourceDeleted = vi.fn();
    vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((resolve) => { resolveInventory = resolve; }));
    vi.mocked(sourceCommandAction).mockResolvedValueOnce({ status: "success", message: "Source removed.", version: 1,
      cleanup: { id: "32345678-1234-1234-1234-123456789abc", project_id: projectId, status: "pending" } });
    render(<SourcesWorkspace projectId={projectId} initialSources={[source]} archived={false}
      onSourcesChanged={onSourcesChanged} onSourceDeleted={onSourceDeleted} />);
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Yes, delete source" })); });

    expect(onSourceDeleted).toHaveBeenCalledExactlyOnceWith(source.id);
    expect(screen.queryByRole("listitem", { name: source.filename })).toBeNull();
    await act(async () => { resolveInventory(new Response(JSON.stringify({ items: [source], playlist_items: [] }))); });

    expect(screen.queryByRole("listitem", { name: source.filename })).toBeNull();
    expect(onSourcesChanged).toHaveBeenCalledExactlyOnceWith([]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("retains the subtitle draft and request key after a returned error, then resends unchanged", async () => {
    vi.mocked(uploadSourceAction).mockResolvedValue({ status: "error", message: "Delivery could not be confirmed.", version: 1 });
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    const file = new File(["WEBVTT"], "owned.vtt");
    fireEvent.change(screen.getByLabelText("SRT / VTT transcript"), { target: { files: [file] } });
    fireEvent.change(screen.getAllByLabelText("Ownership / permission")[0], { target: { value: "owner_upload" } });
    const form = screen.getByRole("form", { name: "Upload transcript" });
    const key = () => (form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value;
    const original = key();
    await act(async () => { fireEvent.submit(form); });
    expect(screen.getByRole("alert")).toHaveTextContent("Delivery could not be confirmed");
    expect(screen.getAllByLabelText("Ownership / permission")[0]).toHaveValue("owner_upload");
    expect((screen.getByLabelText("SRT / VTT transcript") as HTMLInputElement).files?.[0]).toBe(file);
    expect(key()).toBe(original);
    await act(async () => { fireEvent.submit(form); });
    const retried = vi.mocked(uploadSourceAction).mock.calls.at(-1)![1];
    expect(retried.get("idempotency_key")).toBe(original);
    expect(retried.get("authorization_mode")).toBe("owner_upload");
  });

  it("retains metadata URL, rights and request key after a returned error", async () => {
    vi.mocked(metadataSourceAction).mockResolvedValue({ status: "error", message: "Delivery could not be confirmed.", version: 1 });
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    fireEvent.click(screen.getByText("Import YouTube video / playlist metadata"));
    fireEvent.change(screen.getByLabelText("YouTube HTTPS URL"), { target: { value: "https://www.youtube.com/watch?v=abcdefghijk" } });
    fireEvent.change(screen.getAllByLabelText("Ownership / permission")[1], { target: { value: "authorized_upload" } });
    const form = screen.getByRole("form", { name: "Import YouTube metadata" });
    const original = (form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value;
    await act(async () => { fireEvent.submit(form); });
    expect(screen.getByLabelText("YouTube HTTPS URL")).toHaveValue("https://www.youtube.com/watch?v=abcdefghijk");
    expect(screen.getAllByLabelText("Ownership / permission")[1]).toHaveValue("authorized_upload");
    await act(async () => { fireEvent.submit(form); });
    const retried = vi.mocked(metadataSourceAction).mock.calls.at(-1)![1];
    expect(retried.get("idempotency_key")).toBe(original);
    expect(retried.get("authorization_mode")).toBe("authorized_upload");
    expect(retried.get("url")).toBe("https://www.youtube.com/watch?v=abcdefghijk");
  });

  it.each(["upload", "metadata"] as const)("locks the %s draft while pending and resets only after acceptance", async (kind) => {
    const action = kind === "upload" ? vi.mocked(uploadSourceAction) : vi.mocked(metadataSourceAction);
    let accept!: () => void;
    action.mockImplementationOnce(() => new Promise((resolve) => { accept = () => resolve({ status: "success", message: "Source accepted.", version: 1 }); }));
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    fireEvent.click(screen.getByText("Import YouTube video / playlist metadata"));
    const form = screen.getByRole("form", { name: kind === "upload" ? "Upload transcript" : "Import YouTube metadata" });
    const key = () => (form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value;
    const input = screen.getByLabelText(kind === "upload" ? "SRT / VTT transcript" : "YouTube HTTPS URL");
    const rights = screen.getAllByLabelText("Ownership / permission")[kind === "upload" ? 0 : 1];
    const edit = (again = false) => fireEvent.change(input, { target: kind === "upload" ? { files: [new File(["WEBVTT"], "owned.vtt")] } : { value: `https://www.youtube.com/watch?v=${again ? "ABCDEFGHIJK" : "abcdefghijk"}` } });
    edit(); fireEvent.change(rights, { target: { value: "owner_upload" } });
    const original = key();
    act(() => { fireEvent.submit(form); fireEvent.submit(form); });
    expect(action).toHaveBeenCalledTimes(1);
    expect(form).toHaveAttribute("aria-busy", "true");
    expect(input).toBeDisabled(); expect(rights).toBeDisabled();
    expect(screen.getByRole("button", { name: kind === "upload" ? "Uploading…" : "Registering…" })).toBeDisabled();
    await act(async () => { accept(); });
    expect(form).toHaveAttribute("aria-busy", "false");
    expect(rights).toHaveValue(""); expect(key()).toBe("");
    expect(screen.getByRole("button", { name: kind === "upload" ? "Process transcript" : "Import metadata only" })).toBeDisabled();
    if (kind === "metadata") expect(input).toHaveValue("");
    expect(fetch).toHaveBeenCalledTimes(1);
    edit(true);
    expect(key()).not.toBe(original); expect(key()).not.toBe("");
  });

  it("preserves the subtitle association and key through busy and removed playlist snapshots", async () => {
    const lesson: PlaylistItem = { id: "22345678-1234-1234-1234-123456789abc", playlist_source_id: projectId,
      generation: 1, position: 0, video_id: "abcdefghijk", title: "First lesson", transcript_source_id: null };
    vi.mocked(uploadSourceAction).mockResolvedValue({ status: "error", message: "Delivery could not be confirmed.", version: 1 });
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} initialPlaylistItems={[lesson]} archived={false} />);
    fireEvent.change(screen.getByLabelText("SRT / VTT transcript"), { target: { files: [new File(["WEBVTT"], "owned.vtt")] } });
    fireEvent.change(screen.getAllByLabelText("Ownership / permission")[0], { target: { value: "owner_upload" } });
    fireEvent.change(screen.getByLabelText("Transcript belongs to"), { target: { value: lesson.id } });
    const form = screen.getByRole("form", { name: "Upload transcript" });
    const key = () => (form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value;
    const original = key();
    await act(async () => { fireEvent.submit(form); });
    const pending = { ...source, status: "processing", job: { ...source.job!, status: "running", stage: "embedding" } };
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ items: [pending], playlist_items: [{ ...lesson, transcript_source_id: source.id }] }), { status: 200 }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });
    expect(screen.getByLabelText("Transcript belongs to")).toHaveValue(lesson.id);
    expect(screen.getByRole("option", { name: /First lesson/ })).not.toBeDisabled();
    expect(key()).toBe(original);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ items: [], playlist_items: [] }), { status: 200 }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });
    expect(screen.getByLabelText("Transcript belongs to")).toHaveValue(lesson.id);
    expect(screen.getByRole("option", { name: /Previously selected lesson/ })).toBeVisible();
    await act(async () => { fireEvent.submit(form); });
    const retried = vi.mocked(uploadSourceAction).mock.calls.at(-1)![1];
    expect(retried.get("idempotency_key")).toBe(original);
    expect(retried.get("playlist_item_id")).toBe(lesson.id);
    fireEvent.change(screen.getByLabelText("Transcript belongs to"), { target: { value: "" } });
    expect(key()).not.toBe(original);
  });

  it("keeps accepted uploads distinct from a failed source-list refresh", async () => {
    vi.mocked(uploadSourceAction).mockResolvedValueOnce({ status: "success", message: "Transcript accepted.", version: 1 });
    vi.mocked(fetch).mockRejectedValueOnce(new Error("private refresh failure"));
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    fireEvent.change(screen.getByLabelText("SRT / VTT transcript"), { target: { files: [new File(["WEBVTT"], "owned.vtt")] } });
    fireEvent.change(screen.getAllByLabelText("Ownership / permission")[0], { target: { value: "owner_upload" } });
    const form = screen.getByRole("form", { name: "Upload transcript" });
    await act(async () => { fireEvent.submit(form); });
    expect(screen.getByText("Transcript accepted.")).toHaveAttribute("role", "status");
    expect(screen.getByRole("alert")).toHaveTextContent("Sources could not refresh");
    expect(screen.queryByText(/private refresh/)).not.toBeInTheDocument();
    expect((form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Process transcript" })).toBeDisabled();
  });

  it.each(["upload", "metadata"] as const)("retains the %s draft and key when the action rejects unexpectedly", async (kind) => {
    const action = kind === "upload" ? vi.mocked(uploadSourceAction) : vi.mocked(metadataSourceAction);
    action.mockRejectedValueOnce(new Error("private upstream failure"));
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} />);
    fireEvent.click(screen.getByText("Import YouTube video / playlist metadata"));
    const form = screen.getByRole("form", { name: kind === "upload" ? "Upload transcript" : "Import YouTube metadata" });
    const rights = screen.getAllByLabelText("Ownership / permission")[kind === "upload" ? 0 : 1];
    fireEvent.change(screen.getByLabelText(kind === "upload" ? "SRT / VTT transcript" : "YouTube HTTPS URL"),
      { target: kind === "upload" ? { files: [new File(["WEBVTT"], "owned.vtt")] } : { value: "https://www.youtube.com/watch?v=abcdefghijk" } });
    fireEvent.change(rights, { target: { value: "owner_upload" } });
    const original = (form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value;
    await act(async () => { fireEvent.submit(form); });
    expect(screen.getByRole("alert")).toHaveTextContent("may already be queued");
    expect(screen.queryByText(/private upstream/)).not.toBeInTheDocument();
    expect(rights).toHaveValue("owner_upload");
    expect((form.querySelector('[name="idempotency_key"]') as HTMLInputElement).value).toBe(original);
    expect(form).toHaveAttribute("aria-busy", "false");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("links only complete retained galleries and avoids raw-video reprocessing", () => {
    const video = { ...source, kind: "video", filename: "owned.mp4", status: "metadata_ready", frame_count: 2,
      active_generation: null, segment_count: 0, job: { ...source.job!, job_type: "visual_publish", stage: "frames_retained" } };
    const { rerender } = render(<SourcesWorkspace projectId={projectId} initialSources={[video]} archived={false} />);
    expect(screen.getByRole("link", { name: "View selected frames" })).toHaveAttribute("href", `/projects/${projectId}/sources/${source.id}/frames`);
    expect(screen.getByText(/not indexed for questions or citations/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reprocess source" })).toBeNull();
    rerender(<SourcesWorkspace key="pending" projectId={projectId} initialSources={[{ ...video, frame_count: 0 }]} archived={false} />);
    expect(screen.queryByRole("link", { name: "View selected frames" })).toBeNull();
  });
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [source] }) }));
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; };
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("polls original cleanup independently of completed processing, then stops on confirmed deletion", async () => {
    const pending = { ...source, asr_origin: asrOrigin, audio_retention: audioRetention("cleanup_pending") };
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ items: [{ ...pending, audio_retention: audioRetention("deleted") }] }), { status: 200 }));
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false} />);
    expect(screen.getByText(/Physical deletion is pending/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Reindex retained transcript" })).toBeVisible();
    expect(screen.getByText(/Automatically transcribed from audio/)).toBeVisible();
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { vi.advanceTimersByTime(10_000); });
    expect(fetch).not.toHaveBeenCalled();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await act(async () => { fireEvent(document, new Event("visibilitychange")); });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Original audio deletion confirmed.")).toBeVisible();
    await act(async () => { vi.advanceTimersByTime(20_000); });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('keeps polling original video cleanup after indexing finishes, then stops on confirmed deletion', async () => {
    const pending={...source,kind:'video',filename:'owned.mp4',frame_count:2,video_retention:audioRetention('cleanup_pending')};
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({items:[{...pending,video_retention:audioRetention('deleted')}]}),{status:200}));
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false}/>);
    expect(screen.getByText(/Original video retention status also refreshes/)).toBeVisible();
    await act(async()=>{vi.advanceTimersByTime(5000);});
    expect(screen.getByText('Original video deletion confirmed.')).toBeVisible();
    await act(async()=>{vi.advanceTimersByTime(15000);});expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([undefined,null,{enabled:false}])('fails closed when video capability is missing/unavailable/off (%s)',capability=>{
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} videoCapability={capability}/>);
    expect(screen.queryByRole('form',{name:'Upload authorized MP4'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('SRT / VTT transcript')).toBeRequired();
  });
  it('offers explicit video opt-in independently of audio and hides uploads on archived projects',()=>{
    const {rerender}=render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} videoCapability={{enabled:true}}/>);
    expect(screen.getByRole('form',{name:'Upload authorized MP4'})).toBeVisible();
    expect(screen.queryByRole('form',{name:'Upload authorized WAV'})).not.toBeInTheDocument();
    rerender(<SourcesWorkspace projectId={projectId} initialSources={[]} archived videoCapability={{enabled:true}}/>);
    expect(screen.queryByRole('form',{name:'Upload authorized MP4'})).not.toBeInTheDocument();
  });
  it("does not offer unusable retry/reprocess controls for retired original audio", () => {
    const failed = { ...source, kind: "audio", active_generation: null, status: "failed", audio_retention: audioRetention("cleanup_failed"),
      job: { ...source.job!, status: "failed" as const, failure_code: "audio_expired" } };
    render(<SourcesWorkspace projectId={projectId} initialSources={[failed]} archived={true} />);
    expect(screen.getByRole("button", { name: "Retry original audio cleanup" })).toBeVisible();
    expect(screen.getByText(/new transcription requires a new authorized upload/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry processing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reprocess source" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Automatic transcription provenance" })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("shows automatic audio continuation without publishing unfinished evidence", () => {
    const pending = { ...source, kind: "audio", active_generation: null, status: "processing", audio_retention: audioRetention(),
      job: { ...source.job!, status: "pending" as const, stage: "waiting_asr_continuation" } };
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false} />);
    expect(screen.getByText(/Audio window saved/)).toHaveTextContent("Unfinished windows are not tutorial evidence");
    expect(screen.getByRole("button", { name: "Cancel processing" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Read transcript" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry processing" })).not.toBeInTheDocument();
  });

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

  it.each([undefined, null, { enabled: false }])('fails closed when audio capability is off or unavailable (%s)', (capability) => {
    render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} audioCapability={capability} />);
    expect(screen.queryByRole('form', { name: 'Upload authorized WAV' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('SRT / VTT transcript')).toBeRequired();
  });
  it('offers a separate opt-in audio form without widening subtitles and hides both on archived projects', () => {
    const { rerender } = render(<SourcesWorkspace projectId={projectId} initialSources={[]} archived={false} audioCapability={{ enabled: true }} />);
    expect(screen.getByRole('form', { name: 'Upload authorized WAV' })).toBeVisible();
    fireEvent.change(screen.getByLabelText('SRT / VTT transcript'), { target: { files: [new File(['x'.repeat(2_000_001)], 'large.vtt', { type: 'text/vtt' })] } });
    expect(screen.getByRole('alert')).toHaveTextContent('at most 2 MB');
    rerender(<SourcesWorkspace projectId={projectId} initialSources={[]} archived audioCapability={{ enabled: true }} />);
    expect(screen.queryByRole('form', { name: 'Upload authorized WAV' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('SRT / VTT transcript')).not.toBeInTheDocument();
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
    expect(screen.getByRole("link", { name: "Read transcript" })).toHaveAttribute("href", `/projects/${projectId}/sources/${source.id}/transcript?generation=1&page=1`);
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));
    expect(screen.getByRole("dialog", { name: "Delete “tutorial.vtt”?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Keep source" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows ordered videos, truncation, partial failure and an explicit upload association", () => {
    const playlist: SourceItem = { ...source, id: projectId, filename: "Python playlist", kind: "youtube_playlist", provider: "youtube", status: "metadata_ready", active_generation: null, playlist_truncated: true };
    const failed: SourceItem = { ...source, status: "failed", active_generation: null, job: { ...source.job!, status: "failed", failure_code: "invalid_transcript", stage: "failed" } };
    const items: PlaylistItem[] = [
      { id: "22345678-1234-1234-1234-123456789abc", playlist_source_id: playlist.id, generation: 1, position: 2, video_id: "abcdefghijk", title: "Third lesson", transcript_source_id: null },
      { id: "32345678-1234-1234-1234-123456789abc", playlist_source_id: playlist.id, generation: 1, position: 0, video_id: "ABCDEFGHIJK", title: "First lesson", transcript_source_id: failed.id },
    ];
    render(<SourcesWorkspace projectId={projectId} initialSources={[playlist, failed]} initialPlaylistItems={items} archived={false} />);
    expect(screen.getByLabelText("Transcript belongs to")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Transcript belongs to"), { target: { value: items[0].id } });
    expect(screen.getByRole("button", { name: "Process transcript" })).toBeDisabled();
    expect(screen.getByText(/0 of 2 videos have indexed transcripts. 1 failed/)).toBeVisible();
    expect(screen.getByText(/snapshot is truncated/)).toBeVisible();
    expect(screen.getByText(/Other videos remain usable/)).toBeVisible();
    const entries = screen.getByRole("region", { name: "Ordered videos: Python playlist" }).querySelectorAll("ol li");
    expect(entries[0]).toHaveTextContent("First lesson");
    expect(entries[1]).toHaveTextContent("Third lesson");
    expect(entries[1]).toHaveAttribute("value", "3");
    expect(screen.getByRole("button", { name: "Retry processing" })).toBeVisible();
  });

  it("explains that deleting playlist metadata keeps independent transcripts", () => {
    render(<SourcesWorkspace projectId={projectId} initialSources={[{ ...source, kind: "youtube_playlist" }]} archived={true} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete source" }));
    expect(screen.getByText(/keeps separately uploaded transcripts/)).toBeVisible();
  });
  it('announces reindex requirements and retains the recovery control', () => {
    render(<SourcesWorkspace projectId={projectId} initialSources={[{...source,active_embedding_space:'signed-hash-v1:64',reindex_required:true}]} archived={false} />);
    expect(screen.getByText(/Reindex required:/)).toHaveTextContent('Old citations remain inspectable');
    expect(screen.getByRole('button', {name:'Reprocess source'})).toBeVisible();
    expect(screen.getByRole('link', {name:'Read transcript'})).toBeVisible();
  });
  it('announces automatic continuation separately from a failed retry', () => {
    const pending = {...source,status:'processing',job:{...source.job!,status:'pending' as const,stage:'waiting_continuation',processed_segments:64,total_segments:129,delivery_count:1,progress_percent:67}};
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false} />);
    expect(screen.getByText(/64 of 129 segments saved/)).toBeVisible();
    expect(screen.getByText(/continue automatically without consuming a retry/)).toBeVisible();
    expect(screen.queryByRole('button', {name:'Retry processing'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name:'Cancel processing'})).toBeVisible();
  });
  it('explains shared slot waiting without implying extra audio lifetime or indexed evidence', () => {
    const pending = { ...source, kind: 'audio', active_generation: null, audio_retention: audioRetention(),
      job: { ...source.job!, status: 'pending' as const, stage: 'waiting_capacity', attempt_count: 0 } };
    render(<SourcesWorkspace projectId={projectId} initialSources={[pending]} archived={false} audioCapability={{ enabled: true }} />);
    expect(screen.getByText(/Playlist processing slots are busy/)).toHaveTextContent('one-hour original-audio eligibility still includes this waiting time');
    expect(screen.getByText(/Playlist processing slots are busy/)).toHaveTextContent('does not consume a retry');
    expect(screen.queryByRole('link', { name: 'Read transcript' })).not.toBeInTheDocument();
  });
});
