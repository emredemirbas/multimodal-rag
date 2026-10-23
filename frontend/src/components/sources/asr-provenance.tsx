import type { AsrOrigin } from "@/lib/api/provenance-contracts";

export function AsrProvenance({ origin }: { origin: AsrOrigin | null | undefined }) {
  if (!origin) return null;
  return <section className="notice stack" aria-label="Automatic transcription provenance">
    <p>Automatically transcribed from audio · not human-reviewed.</p>
    <p>Speech, code identifiers and timestamps may be wrong. Check important claims against your own original recording. To correct the text, upload an authorized SRT/VTT as a new source; it does not replace existing citations.</p>
    <p className="field-hint">Reindexing uses the retained transcript, not a new transcription. Retired original audio cannot be replayed or transcribed again here.</p>
    <details>
      <summary>Transcription model and version</summary>
      <dl>
        <dt>Provider / model</dt><dd>{origin.provider} / {origin.model}</dd>
        <dt>Model revision</dt><dd className="evidence-text">{origin.revision}</dd>
        <dt>Profile</dt><dd className="evidence-text">{origin.profile}</dd>
        <dt>Engine</dt><dd>{origin.engine}</dd>
        <dt>Requested language</dt><dd>{origin.requested_language === "auto" ? "Automatic detection" : origin.requested_language === "en" ? "English" : "Turkish"}</dd>
        <dt>ASR generation</dt><dd>{origin.generation} (separate from the search-index generation)</dd>
        <dt>Transcript assembly</dt><dd>{origin.assembly_version}</dd>
      </dl>
    </details>
  </section>;
}
