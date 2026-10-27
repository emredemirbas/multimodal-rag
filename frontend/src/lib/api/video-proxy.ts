import 'server-only';
import { ApiError } from '@/lib/api/errors';
import { VIDEO_MAX_BYTES, VIDEO_WIRE_LIMIT, parseVideoReceipt } from '@/lib/api/video-contracts';
import { parseSourceList } from '@/lib/api/source-contracts';

export async function videoRequestBody(request: Request, timeoutMs = 30_000): Promise<FormData> {
  const contentType = request.headers.get('content-type');
  const boundary = contentType?.match(/^multipart\/form-data\s*;\s*boundary=(?:"([a-zA-Z0-9_-]{1,70})"|([a-zA-Z0-9_-]{1,70}))$/i);
  if (!boundary) throw new ApiError({ status: 415, code: 'invalid_video_type' });
  const marker = Buffer.from('--' + (boundary[1] ?? boundary[2]));
  let tail: Buffer = Buffer.alloc(0), markers = 0;
  const reader = request.body?.getReader();
  if (!reader) throw new ApiError({ status: 422, code: 'invalid_video_form' });
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0, interrupted = request.signal.aborted;
  const cancel = () => { interrupted = true; void reader.cancel().catch(() => undefined); };
  const timer = setTimeout(cancel, timeoutMs);
  request.signal.addEventListener('abort', cancel, { once: true });
  try {
    while (!interrupted) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > VIDEO_WIRE_LIMIT) throw new ApiError({ status: 413, code: 'video_too_large' });
      // Bound multipart object count before FormData allocation, including markers
      // split across chunks. Five parts plus the closing marker are sufficient.
      const scan = Buffer.concat([tail, chunk.value]);
      for (let at = scan.indexOf(marker); at !== -1; at = scan.indexOf(marker, at + marker.length)) {
        if (++markers > 6) throw new ApiError({ status: 422, code: 'invalid_video_form' });
      }
      tail = Buffer.from(scan.subarray(Math.max(0, scan.length - marker.length + 1)));
      chunks.push(new Uint8Array(chunk.value));
    }
    if (interrupted) throw new ApiError({ status: 408, code: 'video_upload_timeout' });
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener('abort', cancel);
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  let form: FormData;
  try { form = await new Response(new Blob(chunks), { headers: { 'Content-Type': contentType! } }).formData(); }
  catch { throw new ApiError({ status: 422, code: 'invalid_video_form' }); }
  const fields = ['file', 'authorization_mode', 'language', 'idempotency_key', 'retention_acknowledged'];
  if ([...form.keys()].some((name) => !fields.includes(name)) || fields.some((name) => form.getAll(name).length !== 1)) throw new ApiError({ status: 422, code: 'invalid_video_form' });
  const file = form.get('file'), rights = form.get('authorization_mode'), language = form.get('language'), key = form.get('idempotency_key');
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith('.mp4') || file.name.length > 255
      || /[\x00-\x1f\x7f-\x9f/\\]/.test(file.name) || !['video/mp4', 'application/octet-stream'].includes(file.type)) throw new ApiError({ status: 422, code: 'invalid_video_type' });
  if (!file.size || file.size > VIDEO_MAX_BYTES) throw new ApiError({ status: 413, code: 'video_too_large' });
  if (typeof rights !== 'string' || !['owner_upload', 'authorized_upload', 'licensed_content'].includes(rights)) throw new ApiError({ status: 422, code: 'rights_required' });
  if (typeof language !== 'string' || !['en', 'tr', 'en+tr'].includes(language)) throw new ApiError({ status: 422, code: 'invalid_visual_language' });
  if (typeof key !== 'string' || !/^[a-zA-Z0-9_-]{8,128}$/.test(key) || form.get('retention_acknowledged') !== 'accepted') throw new ApiError({ status: 422, code: 'invalid_video_form' });
  return form;
}

export function videoRegistrationReceipt(value: unknown, projectId: string, form: FormData) {
  try {
    if (!value || typeof value !== 'object') throw new Error();
    const row = value as Record<string, unknown>;
    const source = row.source as Record<string, unknown>, job = row.job as Record<string, unknown>;
    if (!source || !job || source.project_id !== projectId || (job.project_id !== undefined && job.project_id !== projectId) || job.source_id !== source.id
        || job.job_type !== 'visual' || job.generation !== 1 || typeof source.generation !== 'number' || source.generation < 1
        || source.kind !== 'video' || source.provider !== 'upload' || source.authorization_mode !== form.get('authorization_mode')
        || source.filename !== (form.get('file') as File).name || source.parent_playlist_source_id != null) throw new Error();
    const parsed = parseSourceList({ items: [source] })[0];
    if (!parsed.video_retention || parsed.audio_retention || parsed.asr_origin) throw new Error();
    const metadata = source.metadata as Record<string, unknown>;
    if (!metadata || metadata.input_kind !== 'video' || metadata.requested_language !== form.get('language')
        || metadata.visual_quality_approval !== 'not_established') throw new Error();
    return parseVideoReceipt({ project_id: projectId, source_id: source.id, job_id: job.id, deduplicated: row.deduplicated });
  } catch { throw new ApiError({ status: 502, code: 'invalid_api_response' }); }
}
