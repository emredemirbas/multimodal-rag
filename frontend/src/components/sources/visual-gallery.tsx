import Link from "next/link";
import { timestamp } from "@/lib/api/chat-contracts";
import type { VisualGallery as Gallery } from "@/lib/api/visual-contracts";
import { RetainedFrameImage } from "@/components/sources/retained-frame-image";

export function VisualGallery({ projectId, gallery }: { projectId: string; gallery: Gallery }) {
  return <article className="panel stack" aria-labelledby="gallery-title">
    <Link href={`/projects/${projectId}`}>Back to project</Link>
    <h1 id="gallery-title">Selected frames · {gallery.source_filename}</h1>
    <p>These selected grayscale frames and automatic OCR are not human-reviewed. OCR can miss code, punctuation and characters. Uniform sampling can miss useful changes.</p>
    <p>{gallery.searchable ? `OCR is indexed at generation ${gallery.active_index_generation}. Questions use evidence in the matching embedding space; saved citations remain inspectable.` : "This gallery is not indexed for questions or citations yet."} No audio transcription or playable original video is provided.</p>
    {gallery.searchable ? <p className="field-hint">Active OCR embedding space: {gallery.active_embedding_space}</p> : null}
    {!gallery.origin ? <p role="status">No complete retained gallery is available yet. Incomplete processing results are not shown.</p> : <>
      <section aria-label="Automatic visual processing provenance" className="stack">
        <p>Extraction generation {gallery.origin.generation} · gallery generation {gallery.generation} · OCR language {gallery.origin.language}{gallery.origin.language === "en+tr" ? " (experimental combined language)" : ""}</p>
        <p className="field-hint">FFmpeg {gallery.origin.engines.ffmpeg} · Tesseract {gallery.origin.engines.tesseract}</p>
        <p className="field-hint">Processing profile: {gallery.origin.profile} · {gallery.processing_version}</p>
      </section>
      <ol className="source-list" aria-label="Timestamped selected frames">
        {gallery.items.map((frame) => <li key={frame.id} id={`frame-${frame.id}`} className="source-card stack">
          <h2>Frame {frame.ordinal + 1} · {timestamp(frame.timestamp_ms)}</h2>
          <RetainedFrameImage projectId={projectId} frame={frame} />
          <p className="field-hint">Actual decoded timestamp · sampled near {timestamp(frame.sample_target_ms)}</p>
          <h3>Unreviewed OCR text</h3>
          {frame.ocr_text ? <pre className="evidence-text">{frame.ocr_text}</pre> : <p>No OCR text was recognized in this frame. The image may still contain information.</p>}
        </li>)}
      </ol>
    </>}
  </article>;
}
