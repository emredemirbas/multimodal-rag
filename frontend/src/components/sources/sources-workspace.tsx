"use client";

import { useActionState, useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import Link from "next/link";

import { metadataSourceAction, sourceCommandAction, uploadSourceAction } from "@/app/actions/sources";
import { SubmitButton } from "@/components/ui/submit-button";
import { isProcessing, parsePlaylistItems, parseSourceList, type CleanupTicket, type PlaylistItem, type SourceItem } from "@/lib/api/source-contracts";
import { CleanupStatus } from "@/components/sources/cleanup-status";
import { INITIAL_SOURCE_ACTION } from "@/lib/source-action-state";
import { transcriptHref } from "@/lib/api/transcript-contracts";
import { AsrProvenance } from "@/components/sources/asr-provenance";
import { AudioRetentionStatus } from "@/components/sources/audio-retention-status";
import { AudioUpload } from '@/components/sources/audio-upload';
import type { AudioCapability } from '@/lib/api/audio-contracts';
import type { VideoCapability } from '@/lib/api/video-contracts';
import { VideoUpload } from '@/components/sources/video-upload';
import { VideoRetentionStatus } from '@/components/sources/video-retention-status';

const FAILURE_MESSAGES: Record<string, string> = {
  invalid_transcript: "Check cue timestamps and text, then upload a corrected SRT/VTT file.",
  invalid_timeline: "Keep cues in time order and each cue under 60 seconds; upload a corrected file.",
  invalid_encoding: "Save the transcript as UTF-8 and upload it again.",
  storage_unavailable: "Storage is unavailable. Processing retries automatically until its attempt limit.",
  worker_lost: "The worker stopped. Processing will retry or can be retried manually.",
  job_timeout: "Processing took too long. Retry or split the transcript into smaller files.",
  provider_not_configured: "YouTube metadata needs a server-side Data API key. Transcript uploads do not.",
  metadata_unavailable: "Metadata is unavailable. Check the provider configuration or retry later.",
  artifact_integrity: "Transcript integrity verification failed. Upload a new source.",
  local_embeddings_unavailable: "Start local-ai and free resources. Processing retries within its attempt limit.",
  local_embeddings_not_installed: "Explicitly download qwen3-embedding:0.6b in local-ai, then retry processing.",
  local_embeddings_busy: "Local embedding capacity is busy; processing retries automatically within its limit.",
  embedding_model_changed: "Restore the approved embedding model. Different model versions need separate indexes.",
  invalid_embeddings: "The local embedding response could not be validated. Check the local model and retry.",
  semantic_transcript_limit: "This job used the previous local input limit. Retry with resumable processing, or split the file.",
  processing_configuration_changed: "Processing uses a different embedding mode. Restore its original mode and retry, or Reprocess source for a new generation.",
  checkpoint_input_changed: "The parser or transcript changed. Reprocess source to start a fresh generation; saved citations remain unchanged.",
  checkpoint_incomplete: "The saved index is incomplete. Retry processing; the previous active evidence remains unchanged.",
  checkpoint_no_progress: "Processing could not advance. Free local resources and retry; completed batches are saved.",
  embedding_input_limit: "The local model rejected this input. Split the transcript into smaller files.",
  audio_expired: "The original audio expired before processing finished. A new transcription requires a new authorized upload.",
  no_speech_detected: "No speech was detected. No tutorial evidence was invented; check the recording before uploading again.",
  local_asr_unavailable: "Local transcription is unavailable. Processing retries within its attempt and original-expiry limits.",
  local_asr_busy: "Local transcription capacity is busy. Saved windows survive automatic retries until the original expires.",
  audio_integrity: "Original audio integrity verification failed. Upload a new authorized recording.",
  visual_ocr_empty: "No nonblank OCR text was recognized. Inspect the retained frames; no searchable text was invented.",
  invalid_visual_index: "The saved OCR index failed verification. The operator must create a new index from a valid retained gallery; old evidence is unchanged.",
  invalid_visual_provenance: "Visual evidence provenance could not be verified. Inspect source processing before retrying.",
  video_expired: "The original video expired before extraction finished. Upload a new authorized MP4.",
  video_processing_unavailable: "Local visual processing is unavailable. Start local-visual and its worker; retries are bounded by original eligibility.",
  visual_unavailable: "The local visual service is unavailable or differs from the pinned profile. Check local-visual and processing settings.",
  visual_profile_changed: "The accepted OCR profile changed. Restore the pinned profile or upload a new authorized MP4.",
  video_timeout: "Extraction exceeded its delivery limit. Free local resources; automatic retries remain bounded by original expiry.",
  local_visual_unavailable: "The isolated visual service is unavailable. Start local-visual and free local resources; retries are bounded by original expiry.",
  local_visual_busy: "Local visual capacity is busy. Processing retries automatically within its attempt and original-expiry limits.",
  invalid_visual_request: "The native worker rejected this video. Use the supported codec, dimensions, zero-based timeline and duration, then upload a corrected authorized MP4.",
  invalid_visual_response: "The native result failed integrity verification. Inspect local-visual; no unverified OCR was published. A retired original requires a new upload.",
};

function RightsSelect({ id, onChange }: { id: string; onChange?: () => void }) {
  return <div className="field">
    <label htmlFor={id}>Ownership / permission</label>
    <select id={id} name="authorization_mode" required defaultValue="" onChange={onChange}>
      <option value="" disabled>Select the statement that applies</option>
      <option value="owner_upload">I own this content</option>
      <option value="authorized_upload">I am authorized to process this content</option>
      <option value="licensed_content">Its license permits this processing</option>
    </select>
    <p className="field-hint">The transcript is retained for retry/reprocessing and deleted with its source or project.</p>
  </div>;
}

function AddSource({ projectId, sources, playlistItems, onCompleted, audioEnabled, videoEnabled }: { projectId: string; sources: SourceItem[]; playlistItems: PlaylistItem[]; onCompleted: () => Promise<void>; audioEnabled: boolean; videoEnabled: boolean }) {
  const [state, setState] = useState(INITIAL_SOURCE_ACTION);
  const [metadataState, setMetadataState] = useState(INITIAL_SOURCE_ACTION);
  const [uploadKey, setUploadKey] = useState("");
  const [metadataKey, setMetadataKey] = useState("");
  const [fileError, setFileError] = useState("");
  const [fileSelected, setFileSelected] = useState(false);
  const [playlistItemId, setPlaylistItemId] = useState("");
  const [pending, setPending] = useState({ upload: false, metadata: false });
  const busy = useRef({ upload: false, metadata: false });
  const id = useId();

  async function submit(event: FormEvent<HTMLFormElement>, kind: "upload" | "metadata") {
    event.preventDefault();
    if (busy.current[kind] || (kind === "upload" ? !uploadKey || !fileSelected || Boolean(fileError) : !metadataKey)) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    if (kind === "upload") {
      if (playlistItemId) body.set("playlist_item_id", playlistItemId);
      else body.delete("playlist_item_id");
    }
    const previous = kind === "upload" ? state : metadataState;
    const update = kind === "upload" ? setState : setMetadataState;
    busy.current[kind] = true;
    setPending((current) => ({ ...current, [kind]: true }));
    update({ ...previous, status: "idle", message: "" });
    try {
      const next = await (kind === "upload" ? uploadSourceAction : metadataSourceAction)(previous, body);
      update(next);
      if (next.status === "success") {
        // A returned error is still a fulfilled React action: reset only accepted drafts.
        form.reset();
        if (kind === "upload") { setUploadKey(""); setFileSelected(false); setFileError(""); setPlaylistItemId(""); }
        else setMetadataKey("");
        await onCompleted().catch(() => update({ ...next, message: `${next.message} The source list could not refresh; use Refresh sources.` }));
      }
    } catch {
      update({ status: "error", version: previous.version + 1,
        message: "Delivery could not be confirmed. It may already be queued; refresh sources or resend the unchanged draft with the same request key." });
    } finally {
      busy.current[kind] = false;
      setPending((current) => ({ ...current, [kind]: false }));
    }
  }

  return <div className="stack stack--large">
    <form onSubmit={(event) => void submit(event, "upload")} className="stack" aria-label="Upload transcript" aria-busy={pending.upload}>
      <input type="hidden" name="projectId" value={projectId} />
      <input type="hidden" name="idempotency_key" value={uploadKey} />
      <fieldset disabled={pending.upload} className="stack">
      <legend>Authorized transcript</legend>
      <div className="field">
        <label htmlFor={`${id}-file`}>SRT / VTT transcript</label>
        <input id={`${id}-file`} type="file" name="file" accept=".srt,.vtt" required aria-describedby={`${id}-file-help`} aria-invalid={Boolean(fileError)}
          onChange={(event) => {
            setUploadKey(crypto.randomUUID());
            const file = event.target.files?.[0];
            setFileSelected(Boolean(file));
            setFileError(file && (file.size === 0 || file.size > 2_000_000) ? "Choose a non-empty file of at most 2 MB." : "");
          }} />
        <p id={`${id}-file-help`} className="field-hint">UTF-8 text, up to 2 MB. {videoEnabled ? 'Use the separate experimental forms for operator-enabled media; this form accepts subtitles only.' : audioEnabled ? 'Use the separate experimental form below for supported WAV. Video/compressed audio uploads are not supported.' : 'Audio/video uploads are not yet available.'}</p>
      </div>
      <div className="field">
        <label htmlFor={`${id}-playlist-item`}>Transcript belongs to</label>
        <select id={`${id}-playlist-item`} name="playlist_item_id" value={playlistItemId}
          onChange={(event) => { setPlaylistItemId(event.target.value); setUploadKey(crypto.randomUUID()); }}>
          <option value="">Standalone source (not a playlist video)</option>
          {playlistItemId && !playlistItems.some((item) => item.id === playlistItemId)
            ? <option value={playlistItemId}>Previously selected lesson (snapshot changed)</option> : null}
          {playlistItems.map((item) => <option key={item.id} value={item.id} disabled={item.id !== playlistItemId && sources.some((source) => source.id === item.transcript_source_id && isProcessing(source))}>
            {sources.find((source) => source.id === item.playlist_source_id)?.filename} · {item.position + 1}. {item.title}
          </option>)}
        </select>
        <p className="field-hint" aria-live="polite">For a playlist video, confirm that this subtitle describes that video. Replacing an upload preserves its previous independent source.
          {playlistItemId && (!playlistItems.some((item) => item.id === playlistItemId) || playlistItems.some((item) => item.id === playlistItemId && sources.some((source) => source.id === item.transcript_source_id && isProcessing(source))))
            ? " The selected lesson changed or is processing. An unchanged retry can recover an accepted upload; for a new upload select a current available lesson or standalone source." : null}
        </p>
      </div>
      <RightsSelect id={`${id}-rights`} onChange={() => setUploadKey(crypto.randomUUID())} />
      {fileError ? <p role="alert">{fileError}</p> : null}
      <button type="submit" className="button button--primary" disabled={pending.upload || Boolean(fileError) || !uploadKey || !fileSelected}>{pending.upload ? "Uploading…" : "Process transcript"}</button>
      </fieldset>
      <p role={state.status === "error" ? "alert" : "status"}>{state.message}</p>
      <p className="field-hint">If delivery is uncertain, keep this draft unchanged and resend with its existing request key to recover an accepted upload without creating another source.</p>
    </form>
    <details>
      <summary>Import YouTube video / playlist metadata</summary>
      <p>No video, audio or captions are downloaded. Upload an authorized transcript{audioEnabled ? ' or supported WAV' : ''} separately to create indexed evidence. This optional import requires a server-side YouTube Data API key.</p>
      <form onSubmit={(event) => void submit(event, "metadata")} className="stack" aria-label="Import YouTube metadata" aria-busy={pending.metadata}>
        <input type="hidden" name="projectId" value={projectId} />
        <input type="hidden" name="idempotency_key" value={metadataKey} />
        <fieldset disabled={pending.metadata} className="stack">
        <legend>Authorized metadata import</legend>
        <div className="field">
          <label htmlFor={`${id}-url`}>YouTube HTTPS URL</label>
          <input id={`${id}-url`} name="url" type="url" maxLength={2048} required onChange={() => setMetadataKey(crypto.randomUUID())} />
        </div>
        <RightsSelect id={`${id}-metadata-rights`} onChange={() => setMetadataKey(crypto.randomUUID())} />
        <button type="submit" className="button button--secondary" disabled={pending.metadata || !metadataKey}>{pending.metadata ? "Registering…" : "Import metadata only"}</button>
        </fieldset>
        <p role={metadataState.status === "error" ? "alert" : "status"}>{metadataState.message}</p>
      </form>
    </details>
  </div>;
}

function ProcessingControl({ projectId, source, command, label, onCompleted }: {
  projectId: string; source: SourceItem; command: string; label: string; onCompleted: () => Promise<void>;
}) {
  const [state, action] = useActionState(sourceCommandAction, INITIAL_SOURCE_ACTION);
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  useEffect(() => { if (state.status === "success") void onCompleted(); }, [state, onCompleted]);
  return <form action={action} className="stack">
    <input type="hidden" name="projectId" value={projectId} />
    <input type="hidden" name="sourceId" value={source.id} />
    <input type="hidden" name="command" value={command} />
    <input type="hidden" name="idempotency_key" value={`${command}-${source.id}-${source.generation}-${source.job?.attempt_count}-${source.job?.max_attempts}-${id}`} />
    <SubmitButton className="button button--secondary" pendingLabel="Working…">{label}</SubmitButton>
    {state.status === "error" ? <p role="alert">{state.message}</p> : null}
  </form>;
}

function DeleteSource({ projectId, source, onDeleted }: { projectId: string; source: SourceItem; onDeleted: (ticket: CleanupTicket, sourceId: string) => Promise<void> }) {
  const [state, action] = useActionState(sourceCommandAction, INITIAL_SOURCE_ACTION);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (state.status === "success" && state.cleanup?.project_id === projectId) {
      dialog.current?.close();
      void onDeleted(state.cleanup, source.id);
    }
  }, [state, onDeleted, projectId, source.id]);
  return <>
    <button ref={trigger} type="button" className="button button--danger" onClick={() => dialog.current?.showModal()}>Delete source</button>
    <dialog ref={dialog} className="confirmation-dialog" aria-labelledby={`${id}-title`} onClose={() => trigger.current?.focus()}>
      <div className="confirmation-dialog__content">
        <h3 id={`${id}-title`}>Delete “{source.filename}”?</h3>
        <p>Indexed evidence is removed immediately. Retained files are deleted by a tracked cleanup job. This cannot be undone.</p>
        {source.kind === "youtube_playlist" ? <p>Deleting playlist metadata removes its ordered video list, but keeps separately uploaded transcripts, authorized audio and their evidence. Pending audio continues under its own temporary-retention policy.</p> : null}
        <form action={action} className="stack">
          <input type="hidden" name="projectId" value={projectId} />
          <input type="hidden" name="sourceId" value={source.id} />
          <input type="hidden" name="command" value="delete" />
          {state.status === "error" ? <p role="alert">{state.message}</p> : null}
          {state.status === "success" && state.cleanup?.project_id !== projectId ? <p role="alert">Source deletion could not be confirmed for this project. Refresh sources before trying again.</p> : null}
          <div className="form-actions">
            <button type="button" className="button button--secondary" onClick={() => dialog.current?.close()}>Keep source</button>
            <SubmitButton className="button button--danger" pendingLabel="Deleting…">Yes, delete source</SubmitButton>
          </div>
        </form>
      </div>
    </dialog>
  </>;
}

export function SourcesWorkspace({ projectId, initialSources, initialPlaylistItems = [], initialKnownSourceIds = [], archived, initialError = "", audioCapability = { enabled: false }, videoCapability = { enabled: false }, onSourcesChanged, onSourceDeleted }: {
  projectId: string; initialSources: SourceItem[]; initialPlaylistItems?: PlaylistItem[]; archived: boolean; initialError?: string; audioCapability?: AudioCapability | null; videoCapability?: VideoCapability | null;
  onSourcesChanged?: (sources: SourceItem[]) => void;
  onSourceDeleted?: (sourceId: string) => void;
  initialKnownSourceIds?: readonly string[];
}) {
  const [sources, setSources] = useState(initialSources);
  const [playlistItems, setPlaylistItems] = useState(initialPlaylistItems);
  const [error, setError] = useState(initialError);
  const [cleanups, setCleanups] = useState<CleanupTicket[]>([]);
  const inflight = useRef(false);
  const deletedSourceIds = useRef(new Set<string>());
  const knownSourceIds = useRef(new Set([...initialSources.map((source) => source.id), ...initialKnownSourceIds]));
  const heading = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const response = await fetch(`/api/projects/${projectId}/sources`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error("Sources could not refresh. Try again shortly.");
      const payload = await response.json();
      const parsed = parseSourceList(payload);
      const nextItems = parsePlaylistItems(payload);
      if (mounted.current) {
        const present = new Set(parsed.map((source) => source.id));
        for (const id of knownSourceIds.current) {
          if (!present.has(id)) deletedSourceIds.current.add(id);
        }
        const next = parsed.filter((source) => !deletedSourceIds.current.has(source.id));
        for (const source of next) knownSourceIds.current.add(source.id);
        setSources(next); setPlaylistItems(nextItems); setError(""); onSourcesChanged?.(next);
      }
    } catch {
      if (mounted.current) setError("Sources could not refresh. Try again shortly.");
    } finally { inflight.current = false; }
  }, [projectId, onSourcesChanged]);

  const deleted = useCallback(async (ticket: CleanupTicket, sourceId: string) => {
    if (!mounted.current || ticket.project_id !== projectId) return;
    deletedSourceIds.current.add(sourceId);
    setSources((previous) => previous.filter((source) => source.id !== sourceId));
    onSourceDeleted?.(sourceId);
    setCleanups((previous) => [...previous.filter((item) => item.id !== ticket.id), ticket]);
    await refresh();
    heading.current?.focus();
  }, [refresh, projectId, onSourceDeleted]);
  const working = sources.some(isProcessing);
  const cleaningAudio = sources.some((source) => source.audio_retention && ["temporary", "expired", "cleanup_pending"].includes(source.audio_retention.status));
  const cleaningVideo = sources.some((source) => source.video_retention && ["temporary", "expired", "cleanup_pending"].includes(source.video_retention.status));

  useEffect(() => {
    if (!working && !cleaningAudio && !cleaningVideo) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    async function poll() {
      if (document.hidden || stopped) return;
      await refresh();
    }
    function visibility() {
      clearInterval(timer);
      if (!document.hidden) { void poll(); timer = setInterval(() => { void poll(); }, 5_000); }
    }
    if (!document.hidden) timer = setInterval(() => { void poll(); }, 5_000);
    document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [working, cleaningAudio, cleaningVideo, projectId, refresh]);

  return <div className="stack stack--large">
    {archived ? <p>Restore the project to add sources. Existing sources and recovery controls remain available.</p> : <>
      <AddSource projectId={projectId} sources={sources} playlistItems={playlistItems} onCompleted={refresh} audioEnabled={audioCapability?.enabled === true} videoEnabled={videoCapability?.enabled === true} />
      {audioCapability?.enabled ? <AudioUpload projectId={projectId} onCompleted={refresh} playlistItems={playlistItems} sources={sources} /> :
        <p className="field-hint">{audioCapability === null ? 'Audio upload availability could not be verified. Reload this page; transcript uploads remain available.' : 'Experimental local WAV upload is off. The operator must explicitly install ASR weights, start local-asr and opt in before audio can be uploaded. Transcript uploads need none of these steps.'}</p>}
      {videoCapability?.enabled ? <VideoUpload projectId={projectId} onCompleted={refresh} /> :
        <p className="field-hint">{videoCapability === null ? 'Video upload availability could not be verified. Reload this page; transcript uploads remain available.' : 'Experimental local MP4 upload is off. The operator must explicitly start local-visual and its worker, then opt in. No audio transcription or video player is enabled.'}</p>}
    </>}
    <div className="form-actions">
      <h3 ref={heading} tabIndex={-1}>Sources</h3>
      <button className="button button--secondary" type="button" onClick={() => { void refresh(); }}>Refresh sources</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <p role="status" aria-live="polite">{working ? "Processing continues in the background. This list updates every five seconds while visible." : `${sources.length} source${sources.length === 1 ? "" : "s"}. No processing is currently running.`}</p>
    {cleaningAudio ? <p className="field-hint">Original audio retention status also refreshes every five seconds while visible. Expiry is not proof of deletion.</p> : null}
    {cleaningVideo ? <p className="field-hint">Original video retention status also refreshes every five seconds while visible. Expiry is not proof of deletion.</p> : null}
    {sources.filter((source) => source.kind === "youtube_playlist").map((playlist) => {
      const items = playlistItems.filter((item) => item.playlist_source_id === playlist.id).sort((a, b) => a.position - b.position);
      const linked = items.map((item) => sources.find((source) => source.id === item.transcript_source_id));
      const ready = linked.filter((source) => source?.active_generation !== null && source?.active_generation !== undefined && !source.reindex_required).length;
      const failed = linked.filter((source) => source?.job?.status === "failed").length;
      return <section key={playlist.id} className="source-card stack" aria-label={`Ordered videos: ${playlist.filename}`}>
        <h4>{playlist.filename} · ordered videos</h4>
        <p role="status">{ready} of {items.length} videos have indexed transcripts. {failed} failed transcript jobs.</p>
        {playlist.playlist_truncated ? <p role="status">This metadata snapshot is truncated at the import safety limit; it is not the complete playlist.</p> : null}
        {failed > 0 ? <p>Other videos remain usable. Use each source’s recovery controls below or upload corrected subtitles. Retired original audio needs a new authorized WAV upload.</p> : null}
        {items.length === 0 ? <p>No ordered videos are available yet. Wait for metadata processing or reprocess an older metadata import to refresh it.</p> : null}
        <ol>
          {items.map((item, index) => <li key={item.id} value={item.position + 1}>
            <p>{item.title} <span className="field-hint">(video {item.video_id})</span></p>
            <p>{linked[index] ? `${linked[index]!.filename} · ${linked[index]!.job?.stage.replaceAll("_", " ") ?? linked[index]!.status}` : audioCapability?.enabled ? "Authorized transcript or supported WAV required. Select this video in its upload form above." : "Authorized transcript required. Select this video in the upload form above."}</p>
          </li>)}
        </ol>
      </section>;
    })}
    {sources.length === 0 ? <div className="state-panel state-panel--compact"><h4>No sources yet</h4><p>Add an authorized transcript to create timestamped evidence.</p></div> : null}
    <ul className="source-list">
      {sources.map((source) => <li key={source.id} className="source-card stack" aria-label={source.filename}>
        <h4>{source.filename}</h4>
        <p>{source.status.replaceAll("_", " ")} · generation {source.generation} · {source.segment_count} indexed segments</p>
        <AsrProvenance origin={source.asr_origin} />
        {source.audio_retention ? <AudioRetentionStatus projectId={projectId} retention={source.audio_retention} onRefresh={refresh} /> : null}
        {source.video_retention ? <VideoRetentionStatus projectId={projectId} retention={source.video_retention} onRefresh={refresh} /> : null}
        {source.reindex_required ? <p role="status">Reindex required: this source uses a different embedding space and is excluded from current search. {source.kind === "video" ? 'The operator must create a new retained-OCR index job; public video reprocessing is not enabled' : source.job ? (source.asr_origin ? 'Reindex retained transcript' : 'Reprocess source') : 'Upload this validation-only transcript again'}. The source list updates after processing. Old citations remain inspectable.</p> :
          source.active_embedding_space ? <p className="field-hint">Search index: {source.active_embedding_space.startsWith('qwen3-0.6b:') ? 'Qwen3 Embedding 0.6B · 1024 dimensions' : 'Deterministic hash · 64 dimensions'}</p> : null}
        {source.job ? <>
          <label htmlFor={`progress-${source.id}`}>Processing: {source.job.stage.replaceAll("_", " ")} ({source.job.progress_percent}%)</label>
          <progress id={`progress-${source.id}`} max={100} value={source.job.progress_percent} />
          <p className="field-hint">Attempt {source.job.attempt_count} of {source.job.max_attempts}</p>
          {(source.job.total_segments ?? 0) > 0 ? <p role="status" aria-live="polite">{source.job.processed_segments ?? 0} of {source.job.total_segments} segments saved · {source.job.delivery_count ?? 0} processing deliveries. Completed batches survive retries.</p> : null}
          {source.job.stage === 'waiting_continuation' ? <p>Progress saved. Processing will continue automatically without consuming a retry attempt; no action is needed.</p> : null}
          {source.job.stage === 'waiting_asr_continuation' ? <p>Audio window saved. Transcription continues automatically without consuming a retry attempt. Unfinished windows are not tutorial evidence.</p> : null}
          {source.job.stage === 'waiting_visual_continuation' ? <p>Selected frame saved. Preparation continues automatically without consuming a retry attempt. The gallery stays unavailable until every frame is retained.</p> : null}
          {source.job.stage === 'waiting_capacity' ? <p>Playlist processing slots are busy. Waiting does not consume a retry attempt.{source.audio_retention ? ' The one-hour original-audio eligibility still includes this waiting time.' : ''}</p> : null}
        </> : <p className="field-hint">Validation-only source: upload a transcript to use processing controls.</p>}
        {source.status === "metadata_ready" ? <p>{source.kind === "video" ? "Visual preparation is complete, but this video is not indexed for questions or citations. Only fully retained selected frames can be inspected." : "Metadata only. Upload an authorized transcript to create searchable evidence. Playlist videos are not processed automatically."}</p> : null}
          {source.job?.failure_code ? <p role="status">{source.kind === 'video' && source.job.failure_code === 'processing_configuration_changed'
            ? 'Restore the embedding mode pinned when this video was accepted, then retry derived processing as its original initiator. A new retained-OCR index is an internal operator command; public video reprocess is not enabled.'
            : FAILURE_MESSAGES[source.job.failure_code] ?? "Processing could not finish. Retry or upload a corrected source."} ({source.job.failure_code})</p> : null}
        {source.active_generation !== null && source.active_generation !== source.generation ? <p>Previously indexed generation {source.active_generation} remains available{source.reindex_required ? ' for saved citation inspection' : ''} until replacement succeeds.</p> : null}
        <div className="form-actions">
          {source.kind === "video" && (source.frame_count ?? 0) > 0 ? <Link className="button button--secondary" prefetch={false} href={`/projects/${projectId}/sources/${source.id}/frames`}>View selected frames</Link> : null}
          {source.active_generation !== null && (source.kind === undefined || source.kind === "transcript") ?
            <Link className="button button--secondary" prefetch={false} href={transcriptHref(projectId, source.id, source.active_generation)}>Read transcript</Link> : null}
          {isProcessing(source) ? <ProcessingControl projectId={projectId} source={source} command="cancel" label="Cancel processing" onCompleted={refresh} /> : null}
          {source.job && source.kind !== "audio" && (source.kind !== "video" || ["visual_publish", "visual_index", "visual_describe"].includes(source.job.job_type ?? "")) && ["failed", "cancelled"].includes(source.job.status) ? <ProcessingControl projectId={projectId} source={source} command="retry" label="Retry processing" onCompleted={refresh} /> : null}
          {source.job && source.kind !== "audio" && source.kind !== "video" && !isProcessing(source) ? <ProcessingControl projectId={projectId} source={source} command="reprocess" label={source.asr_origin ? "Reindex retained transcript" : "Reprocess source"} onCompleted={refresh} /> : null}
          <DeleteSource projectId={projectId} source={source} onDeleted={deleted} />
        </div>
      </li>)}
    </ul>
    {cleanups.map((ticket) => <CleanupStatus key={ticket.id} initialTicket={ticket} />)}
  </div>;
}
