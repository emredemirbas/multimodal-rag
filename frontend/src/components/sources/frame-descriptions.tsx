"use client";
import Link from "next/link";
import { useActionState,useEffect } from "react";
import { useRouter } from "next/navigation";
import { describeFramesAction, type DescriptionActionState } from "@/app/actions/descriptions";
import { RetainedFrameImage } from "@/components/sources/retained-frame-image";
import { timestamp } from "@/lib/api/chat-contracts";
import type { DescriptionView } from "@/lib/api/description-contracts";
import { galleryHref,type VisualGallery } from "@/lib/api/visual-contracts";
import { ApiError,publicErrorMessage } from "@/lib/api/errors";
function busy(job:DescriptionView["latest_job"]) {return !!job && ["pending","running","retrying"].includes(job.status);}
export function FrameDescriptions({projectId,gallery,view,requestKey}:{projectId:string;gallery:VisualGallery;view:DescriptionView;requestKey:string}) {
  const router=useRouter(), running=busy(view.latest_job)||busy(view.index_job);
  const [state,action,pending]=useActionState<DescriptionActionState,FormData>(describeFramesAction,{status:"idle",message:"",version:0,requestKey});
  useEffect(()=>{
    if (!running) return;
    const timer=window.setInterval(()=>{if(document.visibilityState==="visible") router.refresh();},5000);
    return ()=>window.clearInterval(timer);
  },[running,router]);
  useEffect(()=>{if(state.status==="success") router.refresh();},[state.status,state.version,router]);
  return <article className="panel stack" aria-labelledby="descriptions-title">
    <Link href={galleryHref(projectId,gallery.source_id)}>Back to selected frames</Link>
    <h1 id="descriptions-title">Local image-model descriptions</h1>
    <p>Optional Qwen3.5 vision descriptions interpret retained images, not audio. They may hallucinate or miss code and details. They are unreviewed model interpretations, not verified tutorial facts. Literal OCR stays separate.</p>
    <p>One frame per background delivery, up to 20. CPU processing may take minutes. The model is shared with optional local answers, so busy requests may retry. No paid provider, cloud fallback, automatic download or original-video processing.</p>
    {!view.enabled ? <p role="status">Local frame descriptions are disabled. Explicit local vision-model setup and operator opt-in are required. Previously published descriptions remain readable.</p> : null}
    {!gallery.origin ? <p role="status">No complete retained gallery is available yet.</p> : null}
    {view.enabled && gallery.origin ? <form action={action} className="stack">
      <input type="hidden" name="projectId" value={projectId}/><input type="hidden" name="sourceId" value={gallery.source_id}/>
      <input type="hidden" name="idempotency_key" value={state.requestKey}/>
      <p>Generating creates a new description/index generation from these retained frames. Older successful evidence is preserved. Configured availability is not model readiness or quality approval.</p>
      <button className="button" type="submit" disabled={pending||running}>{pending?"Queueing descriptions…":"Describe retained frames"}</button>
    </form> : null}
    {state.message ? <p role={state.status==="error"?"alert":"status"}>{state.message}</p> : null}
    {view.latest_job ? <section aria-label="Description processing status" className="stack">
      <p role="status">Description job: {view.latest_job.status} · {view.latest_job.processed_segments} of {view.latest_job.total_segments} frames saved.</p>
      {["failed","cancelled"].includes(view.latest_job.status) ? <p role="alert">Descriptions did not finish. Existing evidence is unchanged. {view.latest_job.failure_code ? publicErrorMessage(new ApiError({status:503,code:view.latest_job.failure_code}))+" " : ""}Retry processing from the project to reuse accepted checkpoints, or start a new generation after correcting model setup.</p> : null}
      {view.index_job ? <p role="status">Visual evidence indexing: {view.index_job.status}. {view.index_job.status==="succeeded"?"OCR and non-abstained descriptions are indexed as separately labelled evidence segments.":"Only complete index publication changes search. Recover the current stage from the project."}</p> : null}
      <Link href={`/projects/${projectId}`}>Open project progress, cancel and retry controls</Link>
    </section> : null}
    {!view.origin ? <p role="status">No complete description snapshot has been published. Private partial results are not shown.</p> : <>
      <section aria-label="Image-model description provenance" className="stack">
        <p>Description generation {view.origin.generation} · gallery generation {view.gallery_generation} · index generation {view.index_generation}</p>
        <p className="field-hint">{view.origin.model} · local engine {view.origin.engine} · {view.origin.prompt_version}</p>
        <p className="field-hint">Pinned model digest: {view.origin.model_digest}</p>
        {view.latest_job?.id!==view.origin.job_id ? <p>Showing an earlier complete snapshot while the newer description job is incomplete.</p> : null}
      </section>
      <ol className="source-list" aria-label="Structured frame descriptions">
        {view.items.map((item,index)=><li key={item.frame_id} className="source-card stack">
          <h2>Frame {index+1} · {timestamp(gallery.items[index].timestamp_ms)}</h2>
          <RetainedFrameImage projectId={projectId} frame={gallery.items[index]}/>
          <h3>Unreviewed image-model interpretation</h3>
          {item.description.abstained ? <p>The model abstained: no useful visual description was supported. No description text is indexed for this frame.</p> : <>
            <p>View type: {item.description.kind}</p><p className="evidence-text">{item.description.summary}</p>
            {item.description.details.length ? <ul>{item.description.details.map((detail,i)=><li key={i} className="evidence-text">{detail}</li>)}</ul> : null}
          </>}
          {item.description.uncertainties.length ? <div><h3>Model-reported uncertainty</h3><ul>{item.description.uncertainties.map((value,i)=><li key={i} className="evidence-text">{value}</li>)}</ul></div> : null}
          <h3>Separate literal OCR</h3><pre className="evidence-text">{gallery.items[index].ocr_text||"No OCR text was recognized."}</pre>
        </li>)}
      </ol>
    </>}
  </article>;
}
