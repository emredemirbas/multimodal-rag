import 'server-only';
import { requestJson } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { parseVideoCapability } from '@/lib/api/video-contracts';

export async function getVideoCapability() {
  const payload = await requestJson('/api/v1/ingestion/video-capabilities');
  try { return parseVideoCapability(payload); }
  catch { throw new ApiError({ status: 502, code: 'invalid_api_response' }); }
}
