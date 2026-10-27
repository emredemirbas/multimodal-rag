"use client";
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { VIDEO_MAX_BYTES, parseVideoReceipt } from '@/lib/api/video-contracts';

export function VideoUpload({ projectId, onCompleted }: { projectId: string; onCompleted: () => Promise<void> }) {
  const id = useId();
  const [key, setKey] = useState('');
  const [selected, setSelected] = useState(false);
  const [fileError, setFileError] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  useEffect(() => () => controller.current?.abort(), []);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || !key || !selected || fileError) return;
    const form = event.currentTarget, body = new FormData(form), active = new AbortController();
    controller.current = active; busy.current = true;
    let safeFailure: string | null = null;
    setPending(true); setError(''); setStatus('Uploading the temporary original; frame extraction and OCR indexing run in the background.');
    try {
      const response = await fetch(`/api/projects/${projectId}/sources/video`, { method: 'POST', body,
        signal: AbortSignal.any([active.signal, AbortSignal.timeout(45_000)]), cache: 'no-store' });
      const value: unknown = await response.json();
      if (!response.ok) {
        const message = value && typeof value === 'object' && 'message' in value ? value.message : null;
        safeFailure = typeof message === 'string' && message.length <= 512 ? message : 'Video upload could not be accepted. Check the MP4 and try again.';
        throw new Error();
      }
      const receipt = parseVideoReceipt(value);
      if (receipt.project_id !== projectId) throw new Error();
      setStatus(receipt.deduplicated ? 'This video was already accepted. Its existing source is shown below.' : 'Video accepted. Follow frame extraction, OCR indexing and original cleanup in the source list below.');
      form.reset(); setSelected(false); setKey(''); setFileError('');
      await onCompleted().catch(() => setError('Video accepted, but the source list could not refresh. Use Refresh sources to reconnect.'));
    } catch {
      setStatus('');
      setError(active.signal.aborted ? 'Upload delivery stopped. It may already be queued; refresh sources or resend the unchanged file with the same request key.' :
        safeFailure ?? 'Upload delivery could not be confirmed. It may already be queued; refresh sources or resend the unchanged file with the same request key.');
    } finally { controller.current = null; busy.current = false; setPending(false); }
  }
  return <section className="stack" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`}>Experimental local MP4 frame OCR</h3>
    <p>The operator enabled local visual processing. Availability is not service readiness or OCR quality approval. No paid/cloud fallback, URL downloading or automatic model download.</p>
    <p>100 MB / 10 minutes maximum. H.264/avc1 yuv420p, up to 1080p / 60 fps, unrotated and zero-based timeline. At most 20 selected frames; important changes can be missed. The completed gallery shows the pinned selection method. Audio is ignored, not transcribed. No original-video player or playlist association.</p>
    <form onSubmit={(event) => void upload(event)} className="stack" aria-label="Upload authorized MP4" aria-busy={pending}>
      <input type="hidden" name="idempotency_key" value={key} />
      <fieldset disabled={pending} className="stack">
        <legend>Authorized video and permitted selected-frame retention</legend>
        <div className="field">
          <label htmlFor={`${id}-file`}>MP4 video</label>
          <input id={`${id}-file`} type="file" name="file" accept=".mp4,video/mp4" required aria-invalid={Boolean(fileError)} aria-describedby={`${id}-file-help`}
            onChange={(event) => {
              const file = event.target.files?.[0]; setSelected(Boolean(file)); setKey(crypto.randomUUID());
              setFileError(file && (!file.name.toLowerCase().endsWith('.mp4') || !file.size || file.size > VIDEO_MAX_BYTES) ? 'Choose one non-empty MP4 file of at most 100 MB.' : '');
            }} />
          <p id={`${id}-file-help`} className="field-hint">The container is checked before acceptance; the isolated worker checks actual codec, dimensions, timeline and duration. A filename is not proof of compatibility.</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-rights`}>Video ownership / permission</label>
          <select id={`${id}-rights`} name="authorization_mode" required defaultValue="" onChange={() => setKey(crypto.randomUUID())}>
            <option value="" disabled>Select the statement that applies</option>
            <option value="owner_upload">I own this content</option>
            <option value="authorized_upload">I am authorized to process this content</option>
            <option value="licensed_content">Its license permits this processing</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${id}-language`}>Frame text language</label>
          <select id={`${id}-language`} name="language" required defaultValue="" onChange={() => setKey(crypto.randomUUID())}>
            <option value="" disabled>Select OCR language</option><option value="en">English</option><option value="tr">Turkish</option><option value="en+tr">English + Turkish (experimental; may reduce accuracy)</option>
          </select>
        </div>
        <p id={`${id}-retention-help`}>The original is temporary: processing eligibility expires after one hour, including queue waiting. Completion, cancellation, permanent failure or expiry retires it for tracked deletion. Expiry is not proof of physical deletion; storage/scheduler outages can delay cleanup. Permitted selected frames and literal OCR remain until the source or project is deleted. Extracting retired video again requires a new authorized upload.</p>
        <label htmlFor={`${id}-retention`}><input id={`${id}-retention`} name="retention_acknowledged" value="accepted" type="checkbox" required aria-describedby={`${id}-retention-help`} onChange={() => setKey(crypto.randomUUID())} /> I permit selected-frame/OCR retention and understand temporary-original cleanup</label>
        {fileError ? <p role="alert">{fileError}</p> : null}
        <button type="submit" className="button button--primary" disabled={!selected || Boolean(fileError) || !key}>{pending ? 'Uploading MP4…' : 'Process authorized MP4'}</button>
      </fieldset>
      {pending ? <button type="button" className="button button--secondary" onClick={() => controller.current?.abort()}>Stop video upload delivery</button> : null}
    </form>
    <p role="status" aria-live="polite">{status}</p>
    {error ? <p role="alert">{error}</p> : null}
    <p className="field-hint">Automatic OCR is not human-reviewed. Code, symbols and Turkish characters may be wrong. Inspect the retained frame before relying on its text. No image understanding, speech understanding or scene-recall guarantee is implied.</p>
  </section>;
}
