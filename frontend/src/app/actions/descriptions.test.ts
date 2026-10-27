import { beforeEach,describe,expect,it,vi } from "vitest";
import { describeFramesAction,type DescriptionActionState } from "@/app/actions/descriptions";
import { requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { revalidatePath } from "next/cache";
import { projectId,sourceId } from "../../../test-support/visual-fixture";
import { descriptionJobId } from "../../../test-support/description-fixture";
vi.mock("next/cache",()=>({revalidatePath:vi.fn()}));
vi.mock("@/lib/api/client",()=>({requestJson:vi.fn()}));
const initial:DescriptionActionState={status:"idle",message:"",version:0,requestKey:"stable-description-key"};
function form() {const data=new FormData();data.set("projectId",projectId);data.set("sourceId",sourceId);data.set("idempotency_key",initial.requestKey);return data;}
const receipt={source:{id:sourceId,project_id:projectId},job:{id:descriptionJobId,source_id:sourceId,job_type:"visual_describe"},deduplicated:false};
describe("local description action",()=>{
  beforeEach(()=>vi.clearAllMocks());
  it("submits only scoped ids and the stable key; rotates only on acceptance",async()=>{
    vi.mocked(requestJson).mockResolvedValue(receipt);
    const result=await describeFramesAction(initial,form());
    expect(result.status).toBe("success");expect(result.requestKey).not.toBe(initial.requestKey);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}/descriptions`,{method:"POST",body:JSON.stringify({idempotency_key:initial.requestKey})});
    expect(revalidatePath).toHaveBeenCalledWith(`/projects/${projectId}/sources/${sourceId}/frames/descriptions`);
  });
  it("rejects duplicate or invalid fields before any write",async()=>{
    const data=form();data.append("sourceId",sourceId);
    expect((await describeFramesAction(initial,data)).status).toBe("error");
    expect(requestJson).not.toHaveBeenCalled();
  });
  it.each([null,{}, {...receipt,source:{id:projectId,project_id:projectId}}, {...receipt,job:{...receipt.job,source_id:projectId}}, {...receipt,source:{id:sourceId,project_id:12}}])("does not accept a malformed or foreign receipt",async raw=>{
    vi.mocked(requestJson).mockResolvedValue(raw);
    const result=await describeFramesAction(initial,form());
    expect(result.status).toBe("error");expect(result.requestKey).toBe(initial.requestKey);expect(revalidatePath).not.toHaveBeenCalled();
  });
  it("preserves the key and hides raw errors so an uncertain delivery can replay",async()=>{
    vi.mocked(requestJson).mockRejectedValue(new ApiError({status:503,message:"PRIVATE_NATIVE_ERROR"}));
    const result=await describeFramesAction(initial,form());
    expect(result.status).toBe("error");expect(result.requestKey).toBe(initial.requestKey);expect(result.message).not.toContain("PRIVATE");
  });
});
