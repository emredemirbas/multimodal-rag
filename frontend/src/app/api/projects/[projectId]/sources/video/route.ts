import { NextResponse } from 'next/server';
import { requestJson } from '@/lib/api/client';
import { getVideoCapability } from '@/lib/api/video';
import { videoRegistrationReceipt, videoRequestBody } from '@/lib/api/video-proxy';
import { requireSameOrigin } from '@/lib/api/request-origin';
import { UUID_PATTERN } from '@/lib/api/identifiers';
import { ApiError, publicErrorMessage } from '@/lib/api/errors';

// Bounded buffering is one delivery per server process, not a distributed quota.
let uploading = false;
export async function POST(request: Request, { params }: { params: Promise<{ projectId: string }> }) {
  let acquired = false;
  try {
    const { projectId: rawProject } = await params;
    if (!UUID_PATTERN.test(rawProject)) throw new ApiError({ status: 404 });
    const projectId = rawProject.toLowerCase();
    requireSameOrigin(request);
    if (!(await getVideoCapability()).enabled) throw new ApiError({ status: 503, code: 'video_upload_disabled' });
    if (uploading) throw new ApiError({ status: 429, code: 'video_upload_busy' });
    uploading = acquired = true;
    const form = await videoRequestBody(request);
    const payload = await requestJson(`/api/v1/projects/${projectId}/sources/video`, { method: 'POST', body: form });
    return NextResponse.json(videoRegistrationReceipt(payload, projectId, form), { status: 202, headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    const message = error instanceof ApiError && ['request_timeout', 'upstream_unavailable', 'invalid_api_response'].includes(error.code)
      ? 'Upload delivery could not be confirmed. It may already be queued; refresh sources or resend the unchanged file with the same request key.'
      : publicErrorMessage(error instanceof ApiError && error.code === 'validation_error'
        ? new ApiError({ status: 422, code: 'invalid_video_form' }) : error);
    return NextResponse.json({ message }, { status: error instanceof ApiError ? error.status : 502, headers: { 'Cache-Control': 'no-store' } });
  } finally { if (acquired) uploading = false; }
}
