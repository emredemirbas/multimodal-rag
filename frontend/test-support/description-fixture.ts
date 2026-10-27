import type { DescriptionView } from "../src/lib/api/description-contracts";
import { sourceId,visualFixture } from "./visual-fixture";
export const descriptionJobId="55555555-5555-4555-8555-555555555555";
export const indexJobId="66666666-6666-4666-8666-666666666666";
export function descriptionFixture() {
  return {source_id:sourceId,enabled:true,latest_job:{id:descriptionJobId,source_id:sourceId,generation:3,job_type:"visual_describe",status:"succeeded",stage:"descriptions_ready",
    progress_percent:100,attempt_count:1,max_attempts:3,processed_segments:1,total_segments:1,failure_code:null},
    index_job:{id:indexJobId,source_id:sourceId,generation:4,job_type:"visual_index",status:"succeeded",stage:"ready",progress_percent:100,
      attempt_count:1,max_attempts:3,processed_segments:2,total_segments:2,failure_code:null},
    origin:{job_id:descriptionJobId,generation:3,provider:"ollama-local",model:"qwen3.5:4b",model_digest:"a".repeat(64),engine:"0.40.3",
      prompt_version:"retained-frame-description-v1",completed_at:"2026-10-28T12:00:00Z"},
    gallery_generation:2,index_generation:4,items:[{frame_id:visualFixture().items[0].id,
      description:{kind:"diagram",summary:'<script>PRIVATE</script> Two boxes.',details:["An arrow."],uncertainties:["Purpose is unknown."],abstained:false}}] } satisfies DescriptionView & {
        latest_job:NonNullable<DescriptionView["latest_job"]>&{source_id:string;generation:number};
        index_job:NonNullable<DescriptionView["index_job"]>&{source_id:string;generation:number}};
}
