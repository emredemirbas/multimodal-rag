import Link from "next/link";

export function DemoGuide() {
  return <article className="panel stack stack--large" aria-labelledby="demo-heading">
    <header>
      <p className="eyebrow">No paid services or model download</p>
      <h1 id="demo-heading">Try the keyless demo</h1>
      <p>Follow the existing upload → evidence → question → cleanup workflow with a small,
        repository-authored synthetic transcript. Nothing is created, uploaded or deleted automatically.</p>
    </header>
    <p>This walkthrough assumes the default offline extractive answer mode and deterministic
      hash/lexical retrieval. Check the chat labels. If you already enabled optional local models,
      responses and latency may differ; this guide changes no settings.</p>
    <section aria-labelledby="demo-sample-heading" className="stack">
      <h2 id="demo-sample-heading">1. Download the sample</h2>
      <p>Four authored subtitle cues about FastAPI, a health endpoint, Uvicorn and Pydantic.
        There is no underlying recording or playable video. This is a workflow example,
        not real-tutorial or multimodal quality evidence.</p>
      <div className="form-actions">
        <a className="button" href="/samples/fastapi-intro.vtt" download="fastapi-intro.vtt">Download sample VTT</a>
        <a href="/samples/LICENSE.txt" download="LICENSE.txt">Download sample MIT license</a>
      </div>
    </section>
    <section aria-labelledby="demo-upload-heading" className="stack">
      <h2 id="demo-upload-heading">2. Create a separate demo project and upload</h2>
      <p><Link href="/projects#create-project" prefetch={false}>Create a project</Link> named “FastAPI demo”. In
        Source management, choose the downloaded file under SRT / VTT transcript. Keep
        Transcript belongs to set to Standalone source (not a playlist video).</p>
      <p>For Ownership / permission, explicitly choose “Its license permits this processing”,
        then Process transcript. The sample is distributed under the included MIT license;
        this does not assert ownership or grant rights to unrelated tutorials.</p>
      <p>Wait for ready: the chat source selector updates with the source list, without
        reloading the page. If processing completed but the list is stale, use Refresh sources.
        Choose fastapi-intro.vtt as the Source filter.</p>
    </section>
    <section aria-labelledby="demo-questions-heading" className="stack">
      <h2 id="demo-questions-heading">3. Ask a supported and an unsupported question</h2>
      <ul>
        <li><code>Which endpoint checks service health?</code> — expect the passage describing the health-check endpoint.</li>
        <li><code>What do Pydantic response models validate?</code> — expect the passage about validating and documenting returned data.</li>
        <li><code>How does Kubernetes ingress handle TLS?</code> — expect an evidence limitation with no citations.</li>
      </ul>
      <p>Default answers quote source text rather than generate a general tutorial explanation.
        The queued uploader combines these four cues into one published chunk at 00:01–00:22,
        so both supported answers can cite the same full passage. Citation spans are not word-level timing.</p>
    </section>
    <section aria-labelledby="demo-evidence-heading" className="stack">
      <h2 id="demo-evidence-heading">4. Inspect the evidence and reload history</h2>
      <p>Open a citation and check its source, published generation, 00:01–00:22 span and
        literal transcript text. Use Read transcript to browse without model generation.
        Return to the project and reload: the conversation should still be saved.</p>
      <p>No frame JSON upload, OCR, speech recognition or image-model interpretation is needed.
        Unsupported answers should not gain invented citations.</p>
    </section>
    <section aria-labelledby="demo-cleanup-heading" className="stack">
      <h2 id="demo-cleanup-heading">5. Remove only the demo project</h2>
      <p>Open the demo project’s Delete project control and check the project name in its
        confirmation dialog. Do not delete your other projects. Records become inaccessible
        first; retained files have separate cleanup. Wait for “Retained file cleanup completed.”
        before treating physical file deletion as confirmed.</p>
      <p>This walkthrough does not complete the independent real-example review or choose
        between the RAG portfolio and learning/assessment roadmap.</p>
    </section>
    <Link href="/projects" prefetch={false}>Back to projects</Link>
  </article>;
}
