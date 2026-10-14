import Link from "next/link";
import { timestamp } from "@/lib/api/chat-contracts";
import { transcriptHref, type TranscriptPage } from "@/lib/api/transcript-contracts";

export function TranscriptViewer({ projectId, transcript }: { projectId: string; transcript: TranscriptPage }) {
  const older = transcript.generation !== null && transcript.generation !== transcript.active_generation;
  return <article className="panel stack" aria-labelledby="transcript-title">
    <Link href={`/projects/${projectId}`}>Back to project</Link>
    <p className="eyebrow">Published tutorial transcript</p>
    <h1 id="transcript-title">{transcript.source_filename}</h1>
    {transcript.generation !== null ? <>
      <p>Generation {transcript.generation} · {transcript.total_segments} transcript segments</p>
      <p className="muted">Processing version: {transcript.processing_version}</p>
    </> : null}
    {older ? <div className="notice" role="status">
      <p>You are viewing an older published generation. Its text and evidence links remain unchanged after reprocessing.</p>
      <Link prefetch={false} href={transcriptHref(projectId, transcript.source_id)}>Open latest published transcript</Link>
    </div> : null}
    <p>This is retained tutorial evidence, not external documentation. No playable video was uploaded; timestamps identify the original tutorial interval. Reading this page makes no model calls.</p>
    {transcript.items.length === 0 ? <div className="state-panel state-panel--compact" role="status">
      <h2>No published transcript yet</h2>
      <p>{transcript.source_kind === "transcript" ? "Wait for successful processing, or return to the project for progress and recovery controls. Unfinished batches are not tutorial evidence." : "This source contains metadata only. Upload an authorized SRT/VTT transcript to create tutorial evidence."}</p>
    </div> : <>
      <p>Page {transcript.page} of {transcript.total_pages}</p>
      <ol className="source-list" start={(transcript.page - 1) * transcript.page_size + 1} aria-label="Timestamped transcript segments">
        {transcript.items.map((segment) => <li key={segment.segment_id} className="source-card stack">
          <Link className="citation-link" prefetch={false} href={`/projects/${projectId}/evidence/${segment.segment_id}`}>
            Inspect evidence · {timestamp(segment.start_ms)}–{timestamp(segment.end_ms)}
          </Link>
          <p className="evidence-text">{segment.text}</p>
        </li>)}
      </ol>
      <nav className="form-actions" aria-label="Transcript pages">
        {transcript.page > 1 ? <Link prefetch={false} className="button button--secondary" href={transcriptHref(projectId, transcript.source_id, transcript.generation, transcript.page - 1)}>Previous page</Link> : null}
        <span>Page {transcript.page} of {transcript.total_pages}</span>
        {transcript.page < transcript.total_pages ? <Link prefetch={false} className="button button--secondary" href={transcriptHref(projectId, transcript.source_id, transcript.generation, transcript.page + 1)}>Next page</Link> : null}
      </nav>
    </>}
  </article>;
}
