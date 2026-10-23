import { NextResponse } from 'next/server';
import { requestJson } from '@/lib/api/client';
import { getAudioCapability } from '@/lib/api/audio';
import { audioRegistrationReceipt, audioRequestBody } from '@/lib/api/audio-proxy';
import { requireSameOrigin } from '@/lib/api/request-origin';
import { UUID_PATTERN } from '@/lib/api/identifiers';
import { ApiError, publicErrorMessage } from '@/lib/api/errors';

export async function POST(request: Request, { params }: { params: Promise<{ projectId: string }> }) {
  try {
    const { projectId: rawProject } = await params;
    if (!UUID_PATTERN.test(rawProject)) throw new ApiError({ status: 404 });
    const projectId = rawProject.toLowerCase();
    requireSameOrigin(request);
    if (!(await getAudioCapability()).enabled) throw new ApiError({ status: 503, code: 'audio_upload_disabled' });
    const form = await audioRequestBody(request);
    const playlistItemId = form.get('playlist_item_id');
    const payload = await requestJson(`/api/v1/projects/${projectId}/sources/audio`, { method: 'POST', body: form });
    return NextResponse.json(audioRegistrationReceipt(payload, projectId, typeof playlistItemId === 'string' ? playlistItemId : undefined), { status: 202, headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    // Public messages are application-owned. Never forward raw parser/provider errors.
    const message = error instanceof ApiError && ['request_timeout', 'upstream_unavailable'].includes(error.code)
      ? 'Upload delivery could not be confirmed. It may already be queued; refresh sources or resend the unchanged file with the same request key.'
      : error instanceof ApiError && error.status === 404
        ? 'The project or selected playlist lesson is unavailable. Refresh sources and select a current lesson, or check the project.'
      : publicErrorMessage(error instanceof ApiError && error.code === 'validation_error'
        ? new ApiError({ status: 422, code: 'invalid_audio_form' }) : error);
    return NextResponse.json({ message }, {
      status: error instanceof ApiError ? error.status : 502, headers: { 'Cache-Control': 'no-store' },
    });
  }
}
