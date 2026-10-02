"use client";

import { useActionState, useCallback, useEffect, useId, useRef, useState } from "react";

import { metadataSourceAction, sourceCommandAction, uploadSourceAction } from "@/app/actions/sources";
import { SubmitButton } from "@/components/ui/submit-button";
import { isProcessing, parseSourceList, type CleanupTicket, type SourceItem } from "@/lib/api/source-contracts";
import { CleanupStatus } from "@/components/sources/cleanup-status";
import { INITIAL_SOURCE_ACTION } from "@/lib/source-action-state";

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
};

function RightsSelect({ id }: { id: string }) {
  return <div className="field">
    <label htmlFor={id}>Ownership / permission</label>
    <select id={id} name="authorization_mode" required defaultValue="">
      <option value="" disabled>Select the statement that applies</option>
      <option value="owner_upload">I own this content</option>
      <option value="authorized_upload">I am authorized to process this content</option>
      <option value="licensed_content">Its license permits this processing</option>
    </select>
    <p className="field-hint">The transcript is retained for retry/reprocessing and deleted with its source or project.</p>
  </div>;
}

function AddSource({ projectId, onCompleted }: { projectId: string; onCompleted: () => Promise<void> }) {
  const [state, action] = useActionState(uploadSourceAction, INITIAL_SOURCE_ACTION);
  const [metadataState, metadataAction] = useActionState(metadataSourceAction, INITIAL_SOURCE_ACTION);
  const [uploadKey, setUploadKey] = useState("");
  const [metadataKey, setMetadataKey] = useState("");
  const [fileError, setFileError] = useState("");
  const id = useId();
  useEffect(() => {
    if (state.status === "success" || metadataState.status === "success") void onCompleted();
  }, [state, metadataState, onCompleted]);

  return <div className="stack stack--large">
    <form action={action} className="stack" aria-label="Upload transcript">
      <input type="hidden" name="projectId" value={projectId} />
      <input type="hidden" name="idempotency_key" value={uploadKey} />
      <div className="field">
        <label htmlFor={`${id}-file`}>SRT / VTT transcript</label>
        <input id={`${id}-file`} type="file" name="file" accept=".srt,.vtt" required aria-describedby={`${id}-file-help`} aria-invalid={Boolean(fileError)}
          onChange={(event) => {
            setUploadKey(crypto.randomUUID());
            const file = event.target.files?.[0];
            setFileError(file && (file.size === 0 || file.size > 2_000_000) ? "Choose a non-empty file of at most 2 MB." : "");
          }} />
        <p id={`${id}-file-help`} className="field-hint">UTF-8 text, up to 2 MB. Audio/video uploads are not yet available.</p>
      </div>
      <RightsSelect id={`${id}-rights`} />
      {fileError ? <p role="alert">{fileError}</p> : null}
      <SubmitButton className="button button--primary" pendingLabel="Uploading…" disabled={Boolean(fileError) || !uploadKey}>Process transcript</SubmitButton>
      <p role={state.status === "error" ? "alert" : "status"}>{state.message}</p>
    </form>
    <details>
      <summary>Import YouTube video / playlist metadata</summary>
      <p>No video, audio or captions are downloaded. Upload an authorized transcript separately to create indexed evidence. This optional import requires a server-side YouTube Data API key.</p>
      <form action={metadataAction} className="stack" aria-label="Import YouTube metadata">
        <input type="hidden" name="projectId" value={projectId} />
        <input type="hidden" name="idempotency_key" value={metadataKey} />
        <div className="field">
          <label htmlFor={`${id}-url`}>YouTube HTTPS URL</label>
          <input id={`${id}-url`} name="url" type="url" maxLength={2048} required onChange={() => setMetadataKey(crypto.randomUUID())} />
        </div>
        <RightsSelect id={`${id}-metadata-rights`} />
        <SubmitButton className="button button--secondary" pendingLabel="Registering…" disabled={!metadataKey}>Import metadata only</SubmitButton>
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

function DeleteSource({ projectId, source, onDeleted }: { projectId: string; source: SourceItem; onDeleted: (ticket: CleanupTicket) => Promise<void> }) {
  const [state, action] = useActionState(sourceCommandAction, INITIAL_SOURCE_ACTION);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (state.status === "success" && state.cleanup) {
      dialog.current?.close();
      void onDeleted(state.cleanup);
    }
  }, [state, onDeleted]);
  return <>
    <button ref={trigger} type="button" className="button button--danger" onClick={() => dialog.current?.showModal()}>Delete source</button>
    <dialog ref={dialog} className="confirmation-dialog" aria-labelledby={`${id}-title`} onClose={() => trigger.current?.focus()}>
      <div className="confirmation-dialog__content">
        <h3 id={`${id}-title`}>Delete “{source.filename}”?</h3>
        <p>Indexed evidence is removed immediately. Retained files are deleted by a tracked cleanup job. This cannot be undone.</p>
        <form action={action} className="stack">
          <input type="hidden" name="projectId" value={projectId} />
          <input type="hidden" name="sourceId" value={source.id} />
          <input type="hidden" name="command" value="delete" />
          {state.status === "error" ? <p role="alert">{state.message}</p> : null}
          <div className="form-actions">
            <button type="button" className="button button--secondary" onClick={() => dialog.current?.close()}>Keep source</button>
            <SubmitButton className="button button--danger" pendingLabel="Deleting…">Yes, delete source</SubmitButton>
          </div>
        </form>
      </div>
    </dialog>
  </>;
}

export function SourcesWorkspace({ projectId, initialSources, archived, initialError = "" }: {
  projectId: string; initialSources: SourceItem[]; archived: boolean; initialError?: string;
}) {
  const [sources, setSources] = useState(initialSources);
  const [error, setError] = useState(initialError);
  const [cleanups, setCleanups] = useState<CleanupTicket[]>([]);
  const inflight = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const response = await fetch(`/api/projects/${projectId}/sources`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error("Sources could not refresh. Try again shortly.");
      const next = parseSourceList(await response.json());
      if (mounted.current) { setSources(next); setError(""); }
    } catch {
      if (mounted.current) setError("Sources could not refresh. Try again shortly.");
    } finally { inflight.current = false; }
  }, [projectId]);

  const deleted = useCallback(async (ticket: CleanupTicket) => {
    setCleanups((previous) => [...previous.filter((item) => item.id !== ticket.id), ticket]);
    await refresh();
    heading.current?.focus();
  }, [refresh]);
  const working = sources.some(isProcessing);

  useEffect(() => {
    if (!working) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    async function poll() {
      if (document.hidden || stopped) return;
      if (working) await refresh();
    }
    function visibility() {
      clearInterval(timer);
      if (!document.hidden) { void poll(); timer = setInterval(() => { void poll(); }, 5_000); }
    }
    if (!document.hidden) timer = setInterval(() => { void poll(); }, 5_000);
    document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [working, projectId, refresh]);

  return <div className="stack stack--large">
    {archived ? <p>Restore the project to add sources. Existing sources and recovery controls remain available.</p> : <AddSource projectId={projectId} onCompleted={refresh} />}
    <div className="form-actions">
      <h3 ref={heading} tabIndex={-1}>Sources</h3>
      <button className="button button--secondary" type="button" onClick={() => { void refresh(); }}>Refresh sources</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <p role="status" aria-live="polite">{working ? "Processing continues in the background. This list updates every five seconds while visible." : `${sources.length} source${sources.length === 1 ? "" : "s"}. No processing is currently running.`}</p>
    {sources.length === 0 ? <div className="state-panel state-panel--compact"><h4>No sources yet</h4><p>Add an authorized transcript to create timestamped evidence.</p></div> : null}
    <ul className="source-list">
      {sources.map((source) => <li key={source.id} className="source-card stack" aria-label={source.filename}>
        <h4>{source.filename}</h4>
        <p>{source.status.replaceAll("_", " ")} · generation {source.generation} · {source.segment_count} indexed segments</p>
        {source.job ? <>
          <label htmlFor={`progress-${source.id}`}>Processing: {source.job.stage.replaceAll("_", " ")} ({source.job.progress_percent}%)</label>
          <progress id={`progress-${source.id}`} max={100} value={source.job.progress_percent} />
          <p className="field-hint">Attempt {source.job.attempt_count} of {source.job.max_attempts}</p>
        </> : <p className="field-hint">Validation-only source: upload a transcript to use processing controls.</p>}
        {source.status === "metadata_ready" ? <p>Metadata only. Upload an authorized transcript to create searchable evidence. Playlist videos are not processed automatically.</p> : null}
        {source.job?.failure_code ? <p role="status">{FAILURE_MESSAGES[source.job.failure_code] ?? "Processing could not finish. Retry or upload a corrected source."} ({source.job.failure_code})</p> : null}
        {source.active_generation !== null && source.active_generation !== source.generation ? <p>Previously indexed generation {source.active_generation} remains available until replacement succeeds.</p> : null}
        <div className="form-actions">
          {isProcessing(source) ? <ProcessingControl projectId={projectId} source={source} command="cancel" label="Cancel processing" onCompleted={refresh} /> : null}
          {source.job && ["failed", "cancelled"].includes(source.job.status) ? <ProcessingControl projectId={projectId} source={source} command="retry" label="Retry processing" onCompleted={refresh} /> : null}
          {source.job && !isProcessing(source) ? <ProcessingControl projectId={projectId} source={source} command="reprocess" label="Reprocess source" onCompleted={refresh} /> : null}
          <DeleteSource projectId={projectId} source={source} onDeleted={deleted} />
        </div>
      </li>)}
    </ul>
    {cleanups.map((ticket) => <CleanupStatus key={ticket.id} initialTicket={ticket} />)}
  </div>;
}
