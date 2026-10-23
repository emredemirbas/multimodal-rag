import "server-only";
import { requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { parseAudioCapability } from "@/lib/api/audio-contracts";

export async function getAudioCapability() {
  const payload = await requestJson('/api/v1/ingestion/capabilities');
  try { return parseAudioCapability(payload); }
  catch { throw new ApiError({ status: 502, code: 'invalid_api_response' }); }
}
