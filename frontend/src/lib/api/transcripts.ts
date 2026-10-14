import "server-only";
import { requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { parseTranscriptPage, type TranscriptQuery } from "@/lib/api/transcript-contracts";

export async function getTranscript(projectId: string, sourceId: string, query: TranscriptQuery) {
  const parameters = new URLSearchParams({ page: String(query.page) });
  if (query.generation !== undefined) parameters.set("generation", String(query.generation));
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(sourceId)}/transcript?${parameters}`);
  try {
    const result = parseTranscriptPage(payload);
    if (result.source_id.toLowerCase() !== sourceId.toLowerCase() || result.page !== query.page
        || (query.generation !== undefined && result.generation !== query.generation)) throw new Error("Invalid transcript scope");
    return result;
  } catch (cause) {
    throw new ApiError({ status: 502, code: "invalid_api_response", cause });
  }
}
