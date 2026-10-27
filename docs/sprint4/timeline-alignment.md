# Inspect transcript and frame evidence together

Date: 2026-10-27. Scope: a complete read-only API/web inspection flow, not another
native selection experiment. Keep providers, uploads, retention and defaults unchanged.

The user explicitly chooses an existing transcript/audio source in the same project
and asserts that it describes the same recording. Filenames, playlist membership
and overlapping clocks are not proof. This is **user-asserted temporal alignment**,
not verified audiovisual identity, semantic agreement or a new combined citation.
No pairing is persisted or silently applied to retrieval/answers.

For each retained frame, compare its actual PTS plus a signed offset with published
transcript spans using `start <= point < end`. Positive offset means a later time
in the transcript. Never use a nearest-neighbor fallback or invent a duration for
the image. Published segments can combine cues/bridge gaps; their overlap is not
word-level timing or proof that a phrase was spoken at this exact point. Keep
missing spans visible. Pin both published generations in the
inspection link; old evidence IDs and processing origins remain unchanged.

Use one read-only repeatable-read snapshot with tenant/project/membership/source
checks for both sides. At most 20 frames, five overlapping spans per frame and
4,000 characters per excerpt; explicitly mark both kinds of truncation and link
to the full stable transcript evidence. Reuse existing timeline indexes, gallery
integrity checks and protected image reads. No new record/schema/migration, model,
native work, background job, object access during JSON reads or inference usage.

Deliver from the retained gallery: source/offset/confirmation form, version-pinned
results, literal OCR/transcript excerpts side by side, processing provenance,
matched/unmatched counts, accessible loading/empty/error/retry and image-error
states. Test half-open boundaries, offsets, overlaps/truncation, unpublished and
old generations, replacement, archive, authorization/deletion, response bindings
and literal hostile text. Verify against disposable services, never owner data.

Remaining full Sprint 4 gates stay explicit: image-model descriptions and an
independently reviewed audiovisual/visual quality set. This view does not claim
automatic source verification or complete Alpha 2. Validation follows below.

## Use the view

On a completed video source, open **View selected frames → Align with a transcript**.
Choose a published transcript from this project, confirm the same-recording
assertion and set the offset (0 normally). Positive offsets look later in the
transcript. The initial request selects the current complete generations and
redirects to a URL pinning both; reloading that URL does not silently switch
transcript evidence after reprocessing. Choosing sources/offset again starts a
new comparison. Pairing is only inspection configuration in this URL, not a saved
source relationship or evidence provenance claim.

The scoped API is `GET /api/v1/projects/{project}/sources/{video}/alignment` with
`transcript_source_id`, `assert_same_recording=true`, optional `offset_ms` and either
both generation pins or neither. Unknown/duplicate fields fail. Rights to each
source still come from its separate accepted ingestion; the assertion is not a
new ownership verification. JSON reads fetch no objects or model output. Protected
image requests keep their original authorization/integrity checks and verify the
image's own publication generation, not an unrelated latest manifest.

## Local software validation

- **20 new real-PostgreSQL cases**, including boundary/offset arithmetic, explicit
  gaps, overlap/excerpt bounds, old published generations, private staging, ASR
  origin, snapshot consistency during concurrent deletion, archived reads,
  tenant/project/source/member fences, HTTP validation/privacy and pinned image
  verification. With existing gallery/transcript regression: **59 passed**.
- Final backend regression: **911 passed, zero skipped, 204.76s**, with real worker
  process-loss probes (`TEST_REAL_WORKER=1`) on fresh random-port PG/pgvector,
  Redis and MinIO services, test-only environment/credentials/tmpfs. One upstream
  Starlette/httpx TestClient deprecation warning remains unsuppressed.
- **29 new frontend cases**; final frontend **201 passed in 35 files, 3.93s**.
  Lint/typecheck and the production Docker build pass. Contract/client/page/UI
  checks cover response scope/generation/offset/point binding, pairing confirmation,
  pinned redirect, gaps/negative time/truncation, literal hostile text, safe retry,
  no-complete-gallery/no-transcript states and image failure without losing text.
- An initial overlapping legacy fixture repeated identical timestamp/text IDs,
  violating that legacy path's stable-ID uniqueness; distinct authored labels
  correct the fixture. Initial React lint correctly required moving successful
  JSX rendering outside the data-fetch try block. No assertion, processing limit,
  timeout or authorization check was weakened.

This is stateless inspection: no migration, new inference usage, processing job,
embedding, source relationship, object class, raw retention or retrieval change.
The owner's `.env`, upload/selection flags, services and test/user data are untouched.

## Actual native/application validation

Built separately tagged API/worker and production frontend images, then started
a newly named Compose project with random loopback ports, explicitly test-only
credentials, `--env-file /dev/null` and validated new nonexternal volumes. Native
service remains credential-free/internal/read-only with its existing resource
and socket-denial limits. No owner image tag, service, volume or configuration
was replaced. No model download or paid call.

The updated existing `scripts/smoke_video_workflow.py` passes under **both** actual
selection policies: authored MP4 -> public BFF/API -> native OCR -> gallery/outbox
-> index/citation/PNG, then a separately authorized VTT -> actual subtitle worker
-> temporal API -> production server-rendered chooser and version-pinned timeline.
Uniform has two matched frames; change has one matched/five unmatched frames on
these deliberately sparse labels. A −600000ms offset leaves every frame unmatched.
Literal hostile text is escaped; both processing origins and full stable evidence
links survive. After transcript reprocessing, the pinned view retains the old
segment IDs and reports the newer active generation. Project deletion makes the
alignment/evidence unreadable and confirms all owned objects/rows removed. Only
that newly validated test project and its volumes were removed by the wrapper.

Two initial uniform smoke attempts stopped at the same screen check: the simple
HTTP client did not execute Next's streamed meta/RSC redirect (HTTP 200 under its
loading boundary). The smoke now validates the exact local pinned destination and
explicitly requests it when necessary. The final complete two-policy run passes;
the redirect and actual result assertions remain intact. Failure output now names
only the safe check line/error type, never raw payloads or exception contents.
This is authored workflow evidence, not independent audiovisual quality review.

The separately verified previous hosted baseline is
`322a5208a7e3e3cd99efac5ad1fd4a82250125ee`, all four jobs successful in
[run 40577619469](https://github.com/emredemirbas/multimodal-rag/actions/runs/40577619469).
Neither that previous result nor these local checks certify this new timeline
commit's hosted run. Check its exact SHA after push.
