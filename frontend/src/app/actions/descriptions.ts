"use server";
import { revalidatePath } from "next/cache";
import { requestJson } from "@/lib/api/client";
import { ApiError,publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { descriptionHref } from "@/lib/api/description-contracts";
export interface DescriptionActionState { status:"idle"|"success"|"error";message:string;requestKey:string;version:number }
export async function describeFramesAction(previous:DescriptionActionState,form:FormData):Promise<DescriptionActionState> {
  try {
    function field(name:string) {const values=form.getAll(name); if (values.length!==1 || typeof values[0]!=="string") throw new ApiError({status:422}); return values[0];}
    const project=field("projectId"), source=field("sourceId"), key=field("idempotency_key");
    if (!UUID_PATTERN.test(project) || !UUID_PATTERN.test(source) || !/^[a-zA-Z0-9_-]{8,128}$/.test(key)) throw new ApiError({status:422});
    const raw=await requestJson(`/api/v1/projects/${project}/sources/${source}/descriptions`,{method:"POST",body:JSON.stringify({idempotency_key:key})});
    const receipt=raw as {source?:{id?:string;project_id?:string};job?:{source_id?:string;id?:string;job_type?:string};deduplicated?:boolean};
    if (typeof receipt?.source?.id!=="string" || receipt.source.id.toLowerCase()!==source.toLowerCase()
        || typeof receipt.source.project_id!=="string" || receipt.source.project_id.toLowerCase()!==project.toLowerCase()
        || typeof receipt.job?.source_id!=="string" || receipt.job.source_id.toLowerCase()!==source.toLowerCase()
        || typeof receipt.job.id!=="string" || !UUID_PATTERN.test(receipt.job.id) || receipt.job.job_type!=="visual_describe"
        || typeof receipt.deduplicated!=="boolean") throw new ApiError({status:502,code:"invalid_api_response"});
    revalidatePath(`/projects/${project}`); revalidatePath(descriptionHref(project,source));
    return {status:"success",message:"Description request accepted. Processing continues in the background; old evidence remains available.",version:previous.version+1,requestKey:crypto.randomUUID()};
  } catch(error) {return {...previous,status:"error",message:publicErrorMessage(error),version:previous.version+1};}
}
