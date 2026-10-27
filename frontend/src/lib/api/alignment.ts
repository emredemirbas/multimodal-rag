import "server-only";
import { requestJson } from "@/lib/api/client";
import { alignmentParameters, parseTimelineAlignment, type AlignmentQuery } from "@/lib/api/alignment-contracts";
import { ApiError } from "@/lib/api/errors";

export async function getAlignment(project: string, source: string, query: AlignmentQuery) {
  const params = alignmentParameters(query);
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/alignment?${params}`);
  try {
    const view = parseTimelineAlignment(payload);
    if (view.gallery.source_id.toLowerCase() !== source.toLowerCase()
        || view.transcript.source_id.toLowerCase() !== query.transcript_source_id.toLowerCase()
        || view.offset_ms !== query.offset_ms
        || query.visual_generation !== undefined && view.gallery.generation !== query.visual_generation
        || query.transcript_generation !== undefined && view.transcript.generation !== query.transcript_generation) throw new Error("Wrong alignment binding");
    return view;
  } catch { throw new ApiError({ status: 502, code: "invalid_api_response" }); }
}
