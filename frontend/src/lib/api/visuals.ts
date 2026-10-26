import "server-only";
import { requestJson } from "@/lib/api/client";
import { parseVisualGallery } from "@/lib/api/visual-contracts";
import { ApiError } from "@/lib/api/errors";

export async function getVisualGallery(project: string, source: string) {
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/frames`);
  try {
    const gallery = parseVisualGallery(payload);
    if (gallery.source_id.toLowerCase() !== source.toLowerCase()) throw new Error("Wrong visual source");
    return gallery;
  } catch { throw new ApiError({ status: 502, code: "invalid_api_response" }); }
}
