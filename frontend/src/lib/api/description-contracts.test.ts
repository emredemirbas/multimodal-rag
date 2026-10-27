import { describe,expect,it,vi } from "vitest";
import { parseDescriptionView,parseFrameDescription } from "@/lib/api/description-contracts";
import { parseEvidence } from "@/lib/api/chat-contracts";
import { descriptionFixture } from "../../../test-support/description-fixture";
import { projectId,sourceId,visualFixture } from "../../../test-support/visual-fixture";
vi.mock("@/lib/api/client",()=>({requestJson:vi.fn()}));
import { requestJson } from "@/lib/api/client";
import { getDescriptions } from "@/lib/api/descriptions";
describe("scoped complete image descriptions",()=>{
  it("accepts complete and empty opt-in states without leaking unknown keys",()=>{
    const raw=descriptionFixture();
    expect(parseDescriptionView({...raw,object_key:"PRIVATE"}).items).toEqual(raw.items);
    expect(parseDescriptionView({source_id:sourceId,enabled:false,latest_job:null,index_job:null,origin:null,gallery_generation:null,index_generation:null,items:[]}).items).toEqual([]);
    const next={...raw,latest_job:{...raw.latest_job,id:projectId,generation:5,status:"running"}};
    expect(parseDescriptionView(next).origin?.job_id).toBe(raw.origin.job_id);
  });
  it.each(["duplicate","partial","source","gallery","index","latest","origin-job","model","digest","engine","extra-detail","control","surrogate"])("rejects %s corruption",kind=>{
    const row=descriptionFixture();
    if(kind==="duplicate") row.items.push(row.items[0]);
    if(kind==="partial") Object.assign(row,{origin:null});
    if(kind==="source") row.index_job.source_id=projectId;
    if(kind==="gallery") row.gallery_generation=3;
    if(kind==="index") row.index_job.generation=5;
    if(kind==="latest") row.latest_job.generation=2;
    if(kind==="origin-job") row.origin.job_id=projectId;
    if(kind==="model") Object.assign(row.origin,{model:"cloud-model"});
    if(kind==="digest") row.origin.model_digest="latest";
    if(kind==="engine") row.origin.engine="PRIVATE/path";
    if(kind==="extra-detail") row.items[0].description.details=Array(5).fill("detail");
    if(kind==="control") row.items[0].description.summary="x\u0085";
    if(kind==="surrogate") row.items[0].description.summary="x\ud800";
    expect(()=>parseDescriptionView(row)).toThrow();
  });
  it("requires coherent abstention and preserves bounded unicode literally",()=>{
    const raw=descriptionFixture().items[0].description;
    expect(parseFrameDescription({...raw,summary:"😀".repeat(360)}).summary).toHaveLength(720);
    expect(()=>parseFrameDescription({...raw,abstained:true})).toThrow();
    expect(parseFrameDescription({kind:"unclear",summary:"",details:[],uncertainties:[],abstained:true}).abstained).toBe(true);
  });
  it("binds mixed-version evidence to both extraction and description generations",()=>{
    const origin={...visualFixture().origin!,description:descriptionFixture().origin};
    const evidence={segment_id:projectId,source_id:sourceId,source_filename:"owned.mp4",start_ms:5000,end_ms:5000,modality:"frame",frame_id:visualFixture().items[0].id,
      visual_origin:origin,generation:4,processing_version:"visual-evidence-chunks-v2:g4",text:"Unreviewed image-model description:\ndiagram: Two boxes."};
    expect(parseEvidence(evidence).visual_origin?.description).toEqual(origin.description);
    expect(()=>parseEvidence({...evidence,processing_version:"visual-ocr-chunks-v1:g4"})).toThrow();
    expect(()=>parseEvidence({...evidence,visual_origin:{...origin,description:{...origin.description,generation:4}}})).toThrow();
    expect(()=>parseEvidence({...evidence,visual_origin:visualFixture().origin})).toThrow();
  });
  it("fetches only scoped state and rejects a substituted source",async()=>{
    vi.mocked(requestJson).mockResolvedValue(descriptionFixture());
    expect((await getDescriptions(projectId,sourceId)).source_id).toBe(sourceId);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}/descriptions`);
    vi.mocked(requestJson).mockResolvedValue({...descriptionFixture(),source_id:projectId});
    await expect(getDescriptions(projectId,sourceId)).rejects.toMatchObject({status:502,code:"invalid_api_response"});
  });
});
