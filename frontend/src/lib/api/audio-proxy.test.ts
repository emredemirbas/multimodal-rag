// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { audioRegistrationReceipt, audioRequestBody } from '@/lib/api/audio-proxy';
import { parseAudioCapability, parseAudioReceipt, AUDIO_WIRE_LIMIT } from '@/lib/api/audio-contracts';
import { POST } from '@/app/api/projects/[projectId]/sources/audio/route';
import { getAudioCapability } from '@/lib/api/audio';
import { requestJson } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { projectId, sourceId } from '../../../test-support/transcript-fixture';
import { audioRetention } from '../../../test-support/media-fixture';

vi.mock('server-only', () => ({}));
vi.mock('@/lib/api/audio', () => ({ getAudioCapability: vi.fn() }));
vi.mock('@/lib/api/client', () => ({ requestJson: vi.fn() }));
const jobId = '62345678-1234-1234-1234-123456789abc';
const source = { id: sourceId, project_id: projectId, filename: 'owned.wav', provider: 'upload', kind: 'audio',
  status: 'created', generation: 1, active_generation: null, segment_count: 0, failure_code: null, audio_retention: audioRetention(),
  job: { id: jobId, status: 'pending', stage: 'queued', progress_percent: 0, attempt_count: 0, max_attempts: 3, failure_code: null } };
const registered = { source, job: { id: jobId, source_id: sourceId, generation: 1 }, deduplicated: false };
function form() {
  const data = new FormData();
  data.set('file', new File(['RIFF fixture'], 'owned.wav', { type: 'audio/wav' }));
  data.set('authorization_mode', 'owner_upload'); data.set('language', 'en');
  data.set('idempotency_key', 'stable-audio-key'); data.set('retention_acknowledged', 'accepted');
  return data;
}
function request(body: BodyInit = form(), origin = 'http://localhost:3000') {
  return new Request(`http://0.0.0.0:3000/api/projects/${projectId}/sources/audio`, { method: 'POST', body,
    headers: { Host: 'localhost:3000', Origin: origin } });
}
function post(req: Request, project = projectId) { return POST(req, { params: Promise.resolve({ projectId: project }) }); }

describe('bounded same-origin audio BFF', () => {
  beforeEach(() => { vi.mocked(getAudioCapability).mockReset().mockResolvedValue({ enabled: true }); vi.mocked(requestJson).mockReset().mockResolvedValue(registered); });
  it('verifies fixed operator limits and refuses unsafe capability/receipt shapes', () => {
    const capability = { enabled: true, max_bytes: 20_000_000, max_duration_seconds: 600, processing_ttl_seconds: 3600, encoding: 'pcm-s16le-16000-mono' };
    expect(parseAudioCapability(capability)).toEqual({ enabled: true });
    for (const patch of [{ enabled: 'true' }, { max_bytes: 40_000_000 }, { max_duration_seconds: 1200 }, { encoding: 'mp3' }, { processing_ttl_seconds: 0 }]) {
      expect(() => parseAudioCapability({ ...capability, ...patch })).toThrow();
    }
    expect(() => parseAudioReceipt({ project_id: '../foreign' })).toThrow();
  });
  it('rejects invalid IDs and cross-origin/missing-origin requests before any API call', async () => {
    expect((await post(request(), '../foreign')).status).toBe(404);
    expect((await post(request(form(), 'http://attacker.example'))).status).toBe(403);
    const missing = request(); missing.headers.delete('origin');
    expect((await post(missing)).status).toBe(403);
    expect(getAudioCapability).not.toHaveBeenCalled(); expect(requestJson).not.toHaveBeenCalled();
  });
  it('fails closed on disabled/unavailable capability without consuming the file', async () => {
    vi.mocked(getAudioCapability).mockResolvedValueOnce({ enabled: false });
    const req = request();
    expect((await post(req)).status).toBe(503); expect(req.bodyUsed).toBe(false);
    vi.mocked(getAudioCapability).mockRejectedValueOnce(new Error('private service location'));
    const result = await post(request());
    expect(result.status).toBe(502); expect(await result.text()).not.toContain('private'); expect(requestJson).not.toHaveBeenCalled();
  });
  it('preserves explicit fields and stable key while returning only a scoped receipt', async () => {
    const response = await post(request(), projectId.toUpperCase());
    expect(response.status).toBe(202); expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.json()).toEqual({ project_id: projectId, source_id: sourceId, job_id: jobId, deduplicated: false });
    const [path, options] = vi.mocked(requestJson).mock.calls[0];
    expect(path).toBe(`/api/v1/projects/${projectId}/sources/audio`);
    const uploaded = options?.body as FormData;
    expect(uploaded.get('idempotency_key')).toBe('stable-audio-key'); expect(uploaded.get('language')).toBe('en');
    expect(uploaded.get('retention_acknowledged')).toBe('accepted'); expect(uploaded.has('token')).toBe(false);
  });
  it('rejects malformed media, duplicate/extra fields, rights and policy before forwarding', async () => {
    for (const [key, value] of [['authorization_mode', ''], ['language', 'de'], ['retention_acknowledged', 'no'], ['idempotency_key', 'x'], ['url', 'https://evil.example']]) {
      const data = form(); data.set(key, value); expect((await post(request(data))).status).toBe(422);
    }
    const duplicate = form(); duplicate.append('language', 'tr'); expect((await post(request(duplicate))).status).toBe(422);
    const wrong = form(); wrong.set('file', new File(['x'], 'video.mp4', { type: 'video/mp4' }));
    expect((await post(request(wrong))).status).toBe(422);
    const empty = form(); empty.set('file', new File([], 'empty.wav', { type: 'audio/wav' }));
    expect((await post(request(empty))).status).toBe(413);
    expect((await post(request('not multipart'))).status).toBe(415);
    expect(requestJson).not.toHaveBeenCalled();
  });
  it('bounds actual streamed bytes despite a lying Content-Length and cancels the stream', async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream({ start(c) { c.enqueue(new Uint8Array(AUDIO_WIRE_LIMIT)); c.enqueue(new Uint8Array(1)); }, cancel });
    const req = new Request('http://localhost/api/upload', { method: 'POST', body: stream, duplex: 'half',
      headers: { 'Content-Type': 'multipart/form-data; boundary=owned', 'Content-Length': '1' } } as RequestInit);
    await expect(audioRequestBody(req)).rejects.toMatchObject({ status: 413, code: 'audio_too_large' });
    expect(cancel).toHaveBeenCalledTimes(1);
  });
  it('bounds slow/aborted delivery without parsing unfinished input', async () => {
    const stream = new ReadableStream({ pull() { return new Promise(() => {}); } });
    const req = new Request('http://localhost/api/upload', { method: 'POST', body: stream, duplex: 'half', headers: { 'Content-Type': 'multipart/form-data; boundary=owned' } } as RequestInit);
    await expect(audioRequestBody(req, 5)).rejects.toMatchObject({ status: 408 });
  });
  it('rejects foreign/malformed upstream identities and supports replay after indexing advances', async () => {
    for (const patch of [{ source: { ...source, project_id: sourceId } }, { job: { ...registered.job, source_id: jobId } },
      { job: { ...registered.job, generation: 2 } }, { source: { ...source, audio_retention: null } }, { deduplicated: 'yes' }]) {
      expect(() => audioRegistrationReceipt({ ...registered, ...patch }, projectId)).toThrow();
    }
    expect(audioRegistrationReceipt({ ...registered, source: { ...source, kind: 'transcript', generation: 2,
      job: { ...source.job, id: projectId } }, deduplicated: true }, projectId).job_id).toBe(jobId);
  });
  it('never exposes raw parser/storage/provider errors', async () => {
    vi.mocked(requestJson).mockRejectedValue(new ApiError({ status: 503, code: 'storage_unavailable', message: 'private transcript and secret' }));
    const response = await post(request()); expect(response.status).toBe(503);
    expect(await response.text()).not.toMatch(/private|transcript and secret/);
  });
  it('preserves honest uncertain-delivery recovery and actionable form validation', async () => {
    for (const code of ['request_timeout', 'upstream_unavailable']) {
      vi.mocked(requestJson).mockRejectedValueOnce(new ApiError({ status: 504, code }));
      expect(await (await post(request())).text()).toContain('may already be queued');
    }
    vi.mocked(requestJson).mockRejectedValueOnce(new ApiError({ status: 422, code: 'validation_error' }));
    expect(await (await post(request())).text()).toContain('temporary-retention acknowledgement');
  });
  it('forwards only a canonical optional lesson UUID and verifies the returned association', async () => {
    const item = 'a2345678-1234-1234-1234-123456789abc';
    const linked = { ...source, parent_playlist_source_id: jobId,
      metadata: { playlist_item_id: item, video_id: 'video000000', playlist_generation: 1, alignment: 'user_asserted' } };
    vi.mocked(requestJson).mockResolvedValueOnce({ ...registered, source: linked });
    const data = form(); data.set('playlist_item_id', item.toUpperCase());
    expect((await post(request(data))).status).toBe(202);
    expect((vi.mocked(requestJson).mock.calls[0][1]!.body as FormData).get('playlist_item_id')).toBe(item);
    for (const patch of [{ metadata: { ...linked.metadata, playlist_item_id: jobId } }, { metadata: { ...linked.metadata, alignment: 'verified' } },
      { metadata: { ...linked.metadata, video_id: 'invalid' } }, { parent_playlist_source_id: null }]) {
      expect(() => audioRegistrationReceipt({ ...registered, source: { ...linked, ...patch } }, projectId, item)).toThrow();
    }
    expect(() => audioRegistrationReceipt({ ...registered, source: linked }, projectId)).toThrow();
    // Deleting playlist metadata must not make an accepted independent source unrecoverable.
    expect(audioRegistrationReceipt({ ...registered, deduplicated: true, source: { ...linked, parent_playlist_source_id: null } }, projectId, item).deduplicated).toBe(true);
  });
  it('rejects malformed/duplicate lesson fields and normalizes blank standalone input', async () => {
    for (const value of ['../foreign', 'not-a-uuid', new File(['x'], 'fake.txt')]) {
      const data = form(); data.set('playlist_item_id', value);
      expect((await post(request(data))).status).toBe(422);
    }
    const duplicate = form(); duplicate.append('playlist_item_id', projectId); duplicate.append('playlist_item_id', sourceId);
    expect((await post(request(duplicate))).status).toBe(422);
    expect(requestJson).not.toHaveBeenCalled();
    const blank = form(); blank.set('playlist_item_id', '');
    expect((await post(request(blank))).status).toBe(202);
    expect((vi.mocked(requestJson).mock.calls[0][1]!.body as FormData).has('playlist_item_id')).toBe(false);
    vi.mocked(requestJson).mockRejectedValueOnce(new ApiError({ status: 404 }));
    expect(await (await post(request())).text()).toContain('select a current lesson');
  });
});
