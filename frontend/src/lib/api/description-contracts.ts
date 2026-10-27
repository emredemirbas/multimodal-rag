import { UUID_PATTERN } from "@/lib/api/identifiers";
import { parseDescriptionOrigin, type DescriptionOrigin } from "@/lib/api/visual-contracts";
import type { ProcessingJob } from "@/lib/api/source-contracts";
export interface FrameDescription { kind:"code"|"terminal"|"diagram"|"slide"|"interface"|"other"|"unclear";
  summary:string; details:string[]; uncertainties:string[]; abstained:boolean }
export interface DescriptionView { source_id:string; enabled:boolean; latest_job:ProcessingJob|null; index_job:ProcessingJob|null;
  origin:DescriptionOrigin|null; gallery_generation:number|null; index_generation:number|null;
  items:{frame_id:string;description:FrameDescription}[] }
function record(value:unknown):Record<string,unknown> {
  if (!value || typeof value!=="object" || Array.isArray(value)) throw new Error("Invalid description response");
  return value as Record<string,unknown>;
}
function id(value:unknown):string {
  if (typeof value!=="string" || !UUID_PATTERN.test(value)) throw new Error("Invalid description identifier");
  return value;
}
function integer(value:unknown,min=0,max=2147483647):number {
  if (typeof value!=="number" || !Number.isSafeInteger(value) || value<min || value>max) throw new Error("Invalid description count");
  return value;
}
function text(value:unknown,max:number,empty=false):string {
  if (typeof value!=="string" || value.length>max*2 || Array.from(value).length>max || !empty && !value.trim()
      || /[\p{Cc}\p{Cs}]/u.test(value.replace(/[\n\t]/g,""))) throw new Error("Invalid description text");
  return value;
}
export function parseFrameDescription(value:unknown):FrameDescription {
  const row=record(value);
  if (!["code","terminal","diagram","slide","interface","other","unclear"].includes(String(row.kind))
      || typeof row.abstained!=="boolean" || !Array.isArray(row.details) || row.details.length>4
      || !Array.isArray(row.uncertainties) || row.uncertainties.length>2) throw new Error("Invalid description shape");
  const summary=text(row.summary,360,true), details=row.details.map((v)=>text(v,100)), uncertainties=row.uncertainties.map((v)=>text(v,100));
  if (row.abstained ? row.kind!=="unclear" || summary!=="" || details.length>0 : row.kind==="unclear" || !summary.trim()) throw new Error("Invalid abstention");
  return {kind:row.kind as FrameDescription["kind"],summary,details,uncertainties,abstained:row.abstained};
}
function job(value:unknown,source:string,kind:string):ProcessingJob|null {
  if (value===null) return null;
  const row=record(value);
  if (id(row.source_id).toLowerCase()!==source.toLowerCase() || row.job_type!==kind
      || !["pending","running","retrying","succeeded","failed","cancelled"].includes(String(row.status))) throw new Error("Invalid description job scope");
  integer(row.generation,1);
  return {id:id(row.id),status:row.status as ProcessingJob["status"],job_type:kind,stage:text(row.stage,64),
    progress_percent:integer(row.progress_percent,0,100),attempt_count:integer(row.attempt_count,0,12),max_attempts:integer(row.max_attempts,1,12),
    processed_segments:integer(row.processed_segments,0,10000),total_segments:integer(row.total_segments,0,10000),
    failure_code:row.failure_code===null?null:text(row.failure_code,64)};
}
export function descriptionHref(project:string,source:string) { return `/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/frames/descriptions`; }
export function parseDescriptionView(value:unknown):DescriptionView {
  const row=record(value), source_id=id(row.source_id);
  if (typeof row.enabled!=="boolean" || !Array.isArray(row.items) || row.items.length>20) throw new Error("Invalid description state");
  const origin=row.origin===null?null:parseDescriptionOrigin(row.origin);
  const gallery_generation=row.gallery_generation===null?null:integer(row.gallery_generation,1);
  const index_generation=row.index_generation===null?null:integer(row.index_generation,1);
  const latest_job=job(row.latest_job,source_id,"visual_describe"), index_job=job(row.index_job,source_id,"visual_index");
  if (!origin && (row.items.length || gallery_generation!==null || index_generation!==null || index_job)
      || origin && (!row.items.length || gallery_generation===null || gallery_generation>=origin.generation
        || index_generation===null || index_generation<=origin.generation || !index_job || !latest_job)) throw new Error("Incomplete description publication");
  if (origin) {
    const latest=record(row.latest_job), indexed=record(row.index_job);
    if (indexed.generation!==index_generation || integer(latest.generation,1)<origin.generation
        || (latest.id===origin.job_id && (latest.generation!==origin.generation || latest.status!=="succeeded"))
        || (latest.id!==origin.job_id && integer(latest.generation,1)<=origin.generation)) throw new Error("Invalid description generation binding");
  }
  const seen=new Set<string>();
  const items=row.items.map((value)=>{
    const item=record(value), frame_id=id(item.frame_id);
    if (seen.has(frame_id.toLowerCase())) throw new Error("Duplicate described frame");
    seen.add(frame_id.toLowerCase()); return {frame_id,description:parseFrameDescription(item.description)};
  });
  return {source_id,enabled:row.enabled,origin,gallery_generation,index_generation,latest_job,index_job,items};
}
