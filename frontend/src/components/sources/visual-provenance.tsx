import type { VisualOrigin } from "@/lib/api/visual-contracts";

export function VisualProvenance({ origin }: { origin?: VisualOrigin | null }) {
  if (!origin) return null;
  return <section aria-label="Visual evidence provenance" className="stack">
    <p>Automatic frame OCR · not human-reviewed. Code, punctuation and characters may be wrong. This is text recognized in a selected frame, not speech or image understanding.</p>
    <p className="field-hint">Extraction generation {origin.generation} · OCR language {origin.language} · FFmpeg {origin.engines.ffmpeg} · Tesseract {origin.engines.tesseract}</p>
    <p className="field-hint">Processing profile: {origin.profile}</p>
  </section>;
}
