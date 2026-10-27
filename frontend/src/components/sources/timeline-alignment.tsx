import Link from "next/link";
import { AsrProvenance } from "@/components/sources/asr-provenance";
import { RetainedFrameImage } from "@/components/sources/retained-frame-image";
import { alignmentHref, type TimelineAlignment } from "@/lib/api/alignment-contracts";
import { timestamp } from "@/lib/api/chat-contracts";
import type { SourceItem } from "@/lib/api/source-contracts";
import { transcriptHref } from "@/lib/api/transcript-contracts";
import { galleryHref, visualSelectionNotice } from "@/lib/api/visual-contracts";

export function AlignmentForm({ projectId, sourceId, sources }: { projectId: string; sourceId: string; sources: SourceItem[] }) {
  const available = sources.filter((source) => ["transcript", "audio"].includes(source.kind ?? "") && source.active_generation !== null);
  return <section className="panel stack" aria-labelledby="alignment-title">
    <Link href={galleryHref(projectId, sourceId)}>Back to selected frames</Link>
    <h1 id="alignment-title">Align frames with a transcript</h1>
    <p>Choose an authorized transcript of the same recording. Matching filenames or clocks do not prove that sources belong together. This read-only comparison makes no model calls and does not change search, saved citations or source relationships.</p>
    {!available.length ? <div role="status"><h2>No published transcript available</h2>
      <p>Upload an authorized SRT/VTT transcript, or finish processing an optional WAV source in this project, then return here.</p>
      <Link href={`/projects/${projectId}`}>Open project sources</Link></div> : <form method="get" action={alignmentHref(projectId, sourceId)} className="stack">
      <label htmlFor="alignment-source">Transcript from the same recording</label>
      <select id="alignment-source" name="transcript_source_id" defaultValue="" required aria-describedby="alignment-source-help">
        <option value="" disabled>Choose a published transcript</option>
        {available.map((source) => <option key={source.id} value={source.id}>{source.filename}</option>)}
      </select>
      <p id="alignment-source-help" className="field-hint">The comparison pins the latest published generations of both sources when opened.</p>
      <label htmlFor="alignment-offset">Transcript offset (milliseconds)</label>
      <input id="alignment-offset" name="offset_ms" type="number" min={-600000} max={600000} step={1} defaultValue={0} required aria-describedby="alignment-offset-help" />
      <p id="alignment-offset-help" className="field-hint">Transcript time = frame time + offset. Use 0 for a shared clock; +2000 compares a frame at 00:05 with transcript time 00:07. Range: −600000 to +600000.</p>
      <label><input type="checkbox" name="assert_same_recording" value="true" required /> I assert that this transcript describes the same recording. The application has not verified this relationship.</label>
      <button className="button" type="submit">Compare published evidence</button>
    </form>}
  </section>;
}

function signedTime(value: number) { return value < 0 ? `−${timestamp(-value)}` : timestamp(value); }

export function AlignmentViewer({ projectId, view }: { projectId: string; view: TimelineAlignment }) {
  const { gallery, transcript } = view;
  return <article className="panel stack" aria-labelledby="alignment-title">
    <Link href={galleryHref(projectId, gallery.source_id)}>Back to selected frames</Link>
    <h1 id="alignment-title">Frame and transcript timeline</h1>
    <div className="notice" role="note"><p>User-asserted source pairing, not verified audiovisual identity or semantic agreement. Only published segment timestamps overlap; segments can combine subtitle cues and do not establish word-level timing. A transcript statement is not proof of what the image shows. No nearest-cue substitution is used.</p></div>
    <p>{view.matched_frames} of {gallery.items.length} frames overlap a transcript span; {gallery.items.length - view.matched_frames} have no match. Offset: {view.offset_ms} ms.</p>
    <p>Frames: {gallery.source_filename} · gallery generation {gallery.generation} · extraction generation {gallery.origin!.generation}. {visualSelectionNotice(gallery.origin)}</p>
    <p>Transcript: {transcript.source_filename} · generation {transcript.generation}{transcript.generation !== transcript.active_generation ? " (older published generation)" : ""} · {transcript.processing_version}</p>
    <AsrProvenance origin={transcript.asr_origin} />
    <p className="field-hint">Processing profile: {gallery.origin!.profile}. Automatic OCR is unreviewed; a frame is a point observation, not a continuous visible interval. No audio/video player or image-model description is provided.</p>
    <div className="form-actions">
      <Link prefetch={false} href={alignmentHref(projectId, gallery.source_id)}>Choose sources or offset again</Link>
      <Link prefetch={false} href={transcriptHref(projectId, transcript.source_id, transcript.generation)}>Browse this transcript generation</Link>
    </div>
    <ol className="source-list" aria-label="Aligned frame and transcript evidence">
      {view.items.map((item, index) => <li className="source-card stack" key={item.frame_id} id={`frame-${item.frame_id}`}>
        <h2>Frame {index + 1} · {timestamp(gallery.items[index].timestamp_ms)}</h2>
        <div className="alignment-columns">
          <section className="stack" aria-label={`Frame ${index + 1} image and OCR`}>
            <RetainedFrameImage projectId={projectId} frame={gallery.items[index]} />
            <h3>Unreviewed OCR text</h3>
            {gallery.items[index].ocr_text ? <pre className="evidence-text">{gallery.items[index].ocr_text}</pre> : <p>No OCR text was recognized. The image may still contain information.</p>}
          </section>
          <section className="stack" aria-label={`Frame ${index + 1} overlapping transcript`}>
            <h3>Transcript at {signedTime(item.transcript_time_ms)}</h3>
            {!item.matches.length ? <p>No transcript span contains this timestamp. No text was inferred or copied from a nearby cue.</p> : <ul className="stack">
              {item.matches.map((span) => <li key={span.segment_id}>
                <Link className="citation-link" prefetch={false} href={`/projects/${projectId}/evidence/${span.segment_id}`}>
                  Inspect transcript evidence · {timestamp(span.start_ms)}–{timestamp(span.end_ms)}
                </Link>
                <p className="evidence-text">{span.excerpt}</p>
                {span.text_truncated ? <p className="field-hint">Excerpt shortened to 4,000 characters. Open the evidence link for the full text.</p> : null}
              </li>)}
            </ul>}
            {item.matches_truncated ? <p className="field-hint">Showing the first 5 overlapping spans. Browse this transcript generation for additional evidence; omitted spans are not missing source content.</p> : null}
          </section>
        </div>
      </li>)}
    </ol>
  </article>;
}
