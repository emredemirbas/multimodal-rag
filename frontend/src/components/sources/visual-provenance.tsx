import type { VisualOrigin } from "@/lib/api/visual-contracts";
import { visualSelectionNotice } from "@/lib/api/visual-contracts";

export function VisualProvenance({ origin }: { origin?: VisualOrigin | null }) {
  if (!origin) return null;
  return <section aria-label="Visual evidence provenance" className="stack">
    <p>{origin.description ? "Automatic visual evidence · not human-reviewed. Separate segment labels distinguish literal OCR from image-model descriptions. Descriptions may hallucinate; they are model interpretations, not verified facts or speech." : "Automatic frame OCR · not human-reviewed. Code, punctuation and characters may be wrong. This is text recognized in a selected frame, not speech or image understanding."}</p>
    {origin.description ? <p className="field-hint">Description generation {origin.description.generation} · {origin.description.model} · engine {origin.description.engine} · {origin.description.prompt_version} · model digest {origin.description.model_digest}</p> : null}
    <p className="field-hint">{visualSelectionNotice(origin)}</p>
    <p className="field-hint">Extraction generation {origin.generation} · OCR language {origin.language} · FFmpeg {origin.engines.ffmpeg} · Tesseract {origin.engines.tesseract}</p>
    <p className="field-hint">Processing profile: {origin.profile}</p>
  </section>;
}
