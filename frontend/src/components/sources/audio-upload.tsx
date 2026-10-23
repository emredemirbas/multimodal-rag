"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { AUDIO_MAX_BYTES, parseAudioReceipt } from '@/lib/api/audio-contracts';
import { isProcessing, type PlaylistItem, type SourceItem } from '@/lib/api/source-contracts';

export function AudioUpload({ projectId, onCompleted, playlistItems = [], sources = [] }: {
  projectId: string; onCompleted: () => Promise<void>; playlistItems?: PlaylistItem[]; sources?: SourceItem[];
}) {
  const id = useId();
  const [key, setKey] = useState('');
  const [selected, setSelected] = useState(false);
  const [fileError, setFileError] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [playlistItemId, setPlaylistItemId] = useState('');
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  useEffect(() => () => controller.current?.abort(), []);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || !key || !selected || fileError) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    if (playlistItemId) body.set('playlist_item_id', playlistItemId);
    else body.delete('playlist_item_id');
    const active = new AbortController();
    controller.current = active; busy.current = true;
    let safeFailure: string | null = null;
    setPending(true); setError(''); setStatus('Uploading the temporary original; transcription runs in the background.');
    try {
      const response = await fetch(`/api/projects/${projectId}/sources/audio`, { method: 'POST', body,
        signal: AbortSignal.any([active.signal, AbortSignal.timeout(45_000)]), cache: 'no-store' });
      const value: unknown = await response.json();
      if (!response.ok) {
        const message = value && typeof value === 'object' && 'message' in value ? value.message : null;
        safeFailure = typeof message === 'string' && message.length <= 512 ? message : 'Audio upload could not be accepted. Check the file and try again.';
        throw new Error();
      }
      const receipt = parseAudioReceipt(value);
      if (receipt.project_id !== projectId) throw new Error();
      setStatus(receipt.deduplicated ? 'This upload was already accepted. Its existing source is shown below.' : 'Audio accepted. Follow transcription, indexing and original cleanup in the source list below.');
      form.reset(); setSelected(false); setKey(''); setFileError(''); setPlaylistItemId('');
      await onCompleted().catch(() => setError('Audio accepted, but the source list could not refresh. Use Refresh sources to reconnect.'));
    } catch {
      setStatus('');
      setError(active.signal.aborted ? 'Upload delivery stopped. It may already be queued; refresh sources or resend the unchanged file with the same request key.' :
        safeFailure ??
          'Upload delivery could not be confirmed. It may already be queued; refresh sources or resend the unchanged file with the same request key.');
    } finally { controller.current = null; busy.current = false; setPending(false); }
  }

  return <section className="stack" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`}>Experimental local WAV transcription</h3>
    <p>The operator enabled local ASR. Availability does not guarantee model readiness or recognition accuracy. No paid/cloud fallback or automatic model download.</p>
    <p>20 MB / 10 minutes maximum; WAV signed 16-bit PCM, 16 kHz, mono only. Video, compressed audio and URL downloads are not supported.</p>
    <form onSubmit={(event) => void upload(event)} className="stack" aria-label="Upload authorized WAV" aria-busy={pending}>
      <input type="hidden" name="idempotency_key" value={key} />
      <fieldset disabled={pending} className="stack">
        <legend>Authorized audio and temporary retention</legend>
        <div className="field">
          <label htmlFor={`${id}-file`}>WAV recording</label>
          <input id={`${id}-file`} type="file" name="file" accept=".wav,audio/wav,audio/x-wav" required aria-invalid={Boolean(fileError)} aria-describedby={`${id}-file-help`}
            onChange={(event) => {
              const file = event.target.files?.[0]; setSelected(Boolean(file)); setKey(crypto.randomUUID());
              setFileError(file && (!file.name.toLowerCase().endsWith('.wav') || !file.size || file.size > AUDIO_MAX_BYTES) ? 'Choose one non-empty WAV file of at most 20 MB.' : '');
            }} />
          <p id={`${id}-file-help`} className="field-hint">The server checks the actual PCM encoding and duration; a .wav filename alone is not sufficient.</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-playlist`}>Audio belongs to</label>
          <select id={`${id}-playlist`} name="playlist_item_id" value={playlistItemId} aria-describedby={`${id}-playlist-help`}
            onChange={(event) => { setPlaylistItemId(event.target.value); setKey(crypto.randomUUID()); }}>
            <option value="">Standalone source (not a playlist video)</option>
            {playlistItemId && !playlistItems.some((item) => item.id === playlistItemId)
              ? <option value={playlistItemId}>Previously selected lesson (snapshot changed)</option> : null}
            {playlistItems.map((item) => <option key={item.id} value={item.id}
              disabled={item.id !== playlistItemId && sources.some((source) => source.id === item.transcript_source_id && isProcessing(source))}>
              {sources.find((source) => source.id === item.playlist_source_id)?.filename ?? 'Playlist'} · {item.position + 1}. {item.title}
            </option>)}
          </select>
          <p id={`${id}-playlist-help`} className="field-hint" aria-live="polite">
            This is your assertion that the recording describes the selected video; alignment is not verified. Replacing a terminal upload keeps its previous source and citations.
            {playlistItemId && !playlistItems.some((item) => item.id === playlistItemId)
              ? ' The snapshot changed. An unchanged retry can recover an already accepted upload; for a new upload select a current lesson or standalone source.' : null}
            {playlistItems.some((item) => item.id === playlistItemId && sources.some((source) => source.id === item.transcript_source_id && isProcessing(source)))
              ? ' This lesson is processing. Only an unchanged retry can recover an accepted upload; a different upload must wait or cancel the existing work.' : null}
          </p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-rights`}>Audio ownership / permission</label>
          <select id={`${id}-rights`} name="authorization_mode" required defaultValue="" onChange={() => setKey(crypto.randomUUID())}>
            <option value="" disabled>Select the statement that applies</option>
            <option value="owner_upload">I own this content</option>
            <option value="authorized_upload">I am authorized to process this content</option>
            <option value="licensed_content">Its license permits this processing</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${id}-language`}>Speech language</label>
          <select id={`${id}-language`} name="language" defaultValue="auto" required onChange={() => setKey(crypto.randomUUID())}>
            <option value="auto">Automatic detection</option><option value="en">English</option><option value="tr">Turkish</option>
          </select>
        </div>
        <p id={`${id}-retention-help`}>Original audio is temporary: processing eligibility expires after one hour, including queue waiting. Success, cancellation, permanent failure or expiry retires it for tracked deletion. Scheduler/storage outages can delay physical deletion; inspect its status below. The derived transcript is retained until its source/project is deleted. Transcribing retired audio again requires a new upload.</p>
        <label htmlFor={`${id}-retention`}><input id={`${id}-retention`} name="retention_acknowledged" value="accepted" type="checkbox" required aria-describedby={`${id}-retention-help`} onChange={() => setKey(crypto.randomUUID())} /> I understand the temporary-original retention policy</label>
        {fileError ? <p role="alert">{fileError}</p> : null}
        <button type="submit" className="button button--primary" disabled={!selected || Boolean(fileError) || !key}>{pending ? 'Uploading WAV…' : 'Transcribe authorized WAV'}</button>
      </fieldset>
      {pending ? <button type="button" className="button button--secondary" onClick={() => controller.current?.abort()}>Stop upload delivery</button> : null}
    </form>
    <p role="status" aria-live="polite">{status}</p>
    {error ? <p role="alert">{error}</p> : null}
    <p className="field-hint">Automatic transcripts are not human-reviewed. Speech, code identifiers and timestamps can be wrong. Inspect the evidence and upload corrected authorized SRT/VTT text when needed. Reindexing does not transcribe the recording again.</p>
  </section>;
}
