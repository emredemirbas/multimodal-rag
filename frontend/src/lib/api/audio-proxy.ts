import "server-only";
import { ApiError } from "@/lib/api/errors";
import { AUDIO_MAX_BYTES, AUDIO_WIRE_LIMIT, parseAudioReceipt } from "@/lib/api/audio-contracts";
import { parseSourceList } from "@/lib/api/source-contracts";

export async function audioRequestBody(request: Request, timeoutMs = 30_000): Promise<FormData> {
  const contentType = request.headers.get('content-type');
  if (!contentType || !/^multipart\/form-data\s*;\s*boundary=/i.test(contentType) || contentType.length > 256) throw new ApiError({ status: 415, code: 'invalid_audio_type' });
  const reader = request.body?.getReader();
  if (!reader) throw new ApiError({ status: 422, code: 'invalid_audio_form' });
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
      if (size > AUDIO_WIRE_LIMIT) throw new ApiError({ status: 413, code: 'audio_too_large' });
      chunks.push(new Uint8Array(chunk.value));
    }
    if (interrupted) throw new ApiError({ status: 408, code: 'audio_upload_timeout' });
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener('abort', cancel);
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  let form: FormData;
  try { form = await new Response(new Blob(chunks), { headers: { 'Content-Type': contentType } }).formData(); }
  catch { throw new ApiError({ status: 422, code: 'invalid_audio_form' }); }
  const fields = ['file', 'authorization_mode', 'language', 'idempotency_key', 'retention_acknowledged'];
  if ([...form].length !== fields.length || fields.some((name) => form.getAll(name).length !== 1)) throw new ApiError({ status: 422, code: 'invalid_audio_form' });
  const file = form.get('file'), rights = form.get('authorization_mode'), language = form.get('language'), key = form.get('idempotency_key');
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith('.wav') || file.name.length > 255
      || /[\x00-\x1f]/.test(file.name) || !['audio/wav', 'audio/x-wav', 'audio/wave', 'application/octet-stream'].includes(file.type)) throw new ApiError({ status: 422, code: 'invalid_audio_type' });
  if (!file.size || file.size > AUDIO_MAX_BYTES) throw new ApiError({ status: 413, code: 'audio_too_large' });
  if (typeof rights !== 'string' || !['owner_upload', 'authorized_upload', 'licensed_content'].includes(rights)) throw new ApiError({ status: 422, code: 'rights_required' });
  if (typeof language !== 'string' || !['auto', 'en', 'tr'].includes(language)) throw new ApiError({ status: 422, code: 'invalid_asr_language' });
  if (typeof key !== 'string' || !/^[a-zA-Z0-9_-]{8,128}$/.test(key) || form.get('retention_acknowledged') !== 'accepted') throw new ApiError({ status: 422, code: 'invalid_audio_form' });
  return form;
}

export function audioRegistrationReceipt(value: unknown, projectId: string) {
  if (!value || typeof value !== 'object') throw new ApiError({ status: 502 });
  const row = value as Record<string, unknown>;
  const source = row.source as Record<string, unknown> | undefined;
  const job = row.job as Record<string, unknown> | undefined;
  try {
    if (!source || !job || source.project_id !== projectId || job.source_id !== source.id
        || typeof job.generation !== 'number' || !Number.isSafeInteger(job.generation) || job.generation < 1
        || typeof source.generation !== 'number' || job.generation > source.generation) throw new Error();
    const parsed = parseSourceList({ items: [source] })[0];
    if (!parsed.audio_retention || !['audio', 'transcript'].includes(parsed.kind ?? '')) throw new Error();
    return parseAudioReceipt({ project_id: projectId, source_id: source.id, job_id: job.id, deduplicated: row.deduplicated });
  } catch { throw new ApiError({ status: 502, code: 'invalid_api_response' }); }
}
