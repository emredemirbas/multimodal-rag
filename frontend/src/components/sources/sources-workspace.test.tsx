import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesWorkspace } from "@/components/sources/sources-workspace";
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
