import "server-only";
import { requestJson } from "@/lib/api/client";
import { parseDescriptionView } from "@/lib/api/description-contracts";
import { ApiError } from "@/lib/api/errors";
export async function getDescriptions(project:string,source:string) {
  const raw=await requestJson(`/api/v1/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/descriptions`);
  try {
    const view=parseDescriptionView(raw);
    if (view.source_id.toLowerCase()!==source.toLowerCase()) throw new Error("Wrong description source");
    return view;
  } catch {throw new ApiError({status:502,code:"invalid_api_response"});}
}
