# Data model and API outline

Names are provisional. Prefer stable domain concepts over provider-specific names.

## Entity groups

### Identity and tenancy

- `users`
- `tenants`
- `memberships`
- `sessions` or external identity references

### Workspace

- `projects`
- `project_settings`
- `learner_profiles`
- `progress_events`

### Sources and processing

- `sources`
- `playlists`
- `videos`
- `source_artifacts`
- `processing_jobs`
- `processing_attempts`
- `document_versions`

The authorized-transcript Sprint 4 slice adds `playlist_items` metadata snapshots,
the last successful snapshot generation and scoped parent playlist references.
`GET .../sources` returns ordered `playlist_items` alongside sources.
Upload multipart forms may include `playlist_item_id` to atomically associate an
authorized subtitle with a current video entry. Reprocessing playlist metadata
refreshes its snapshot; matching item/video identities preserve upload links.
Metadata-only playlist deletion unlinks, but does not delete, independent uploads.
See ADR 0014 for concurrency, truncation and migration compatibility.

Experimental WAV registration now uses the same optional current item. The legacy
`transcript_source_id` column can refer to a pending audio source which becomes a
transcript only after validated VTT adoption; unpublished speech is never evidence.
Playlist association metadata merges with audio metadata and remains the original
user assertion after snapshot refresh/reindex. ASR/index claims share the same
per-playlist live-lease cap. Metadata deletion unlinks, but does not cancel, the
independent audio source. Existing FKs/schema suffice; no migration is rewritten.

Suggested source fields:

- `id`, `tenant_id`, `project_id`;
- `kind`, `provider`, `canonical_external_id`;
- `authorization_mode`, `license_mode`;
- `status`, `failure_code`, `failure_detail`;
- `processing_version`, `metadata`;
- `created_at`, `updated_at`, `deleted_at`.

### Retrieval

- `content_segments`
- `segment_evidence`
- `frames`
- `embeddings`
- `retrieval_runs`

A content segment should retain:

- source/video identity;
- start and end timestamps;
- normalized text;
- topic/section label;
- modality flags;
- OCR and visual description references;
- stable provenance;
- processing and embedding versions.

Do not store an embedding without the model identifier and dimension/version metadata.

Migration 0007 preserves old 64-D evidence and adds immutable embedding-space
identity to segments, processing versions, usage and retrieval attribution.
The vector column permits separately filtered 64/1024-D rows; a dimension/space
constraint rejects incompatible writes. Exact distance runs only after a
MATERIALIZED tenant/project/active-generation/source/space/dimension filter.
Model manifest, query-template version and dimensions define the semantic space.
Source inventory exposes `active_embedding_space` and computed `reindex_required`;
runtime exposes configured retrieval mode/space. Old evidence inspection does not
require the current space. Local query and document token counts are separate from
answer tokens. Unknown counts remain null; zero billed API cost is explicit.

Migration 0008 adds scoped private `embedding_checkpoints`, a job's pinned target
space, ordered chunk manifest, saved/total counts and independent delivery count.
The historical `processing_attempts.attempt_number` now tracks delivery sequence;
`attempt_count` tracks bounded failure attempts. Successful unfinished deliveries
close as `checkpointed` and requeue atomically. The existing Job API adds
`processed_segments`, `total_segments` and `delivery_count`; no staging text or
vector is exposed. Final promotion removes staging in the same activation
transaction. Cancel preserves it for retry; reprocess discards unfinished staging;
source/project cascades remove it. Usage aggregates accepted batch tokens and
delivery durations, not queue waiting time. See ADR 0017.

Migration 0009 is index-only: a partial chronological transcript index under
tenant/project/source/generation accelerates published timeline browsing. No
evidence is modified, recomputed or duplicated.

Migration 0010 adds private `asr_runs`/`asr_windows`, tied by composite FK to
tenant/project/job/source/generation. Runs pin the original digest/frame count,
requested language, approved model/engine/profile and VTT assembly version.
At most twenty strict windows advance an ordered cursor with accepted input
frames/model duration and payload checksums. No token counts are fabricated.
Only complete validated runs can return a derived VTT; this does not publish an
artifact/index or complete a job. Source/project deletion cascades private text.
This checkpoint component alone did not expose original audio. ADR 0020's later
opt-in upload route now calls the durable registration boundary described below.

Migrations 0011/0012 add scoped `audio_inputs`, cleanup ownership, ASR completion/
downstream-job metadata and ASR origin FKs on retained artifacts and processing
versions. Originals use a separate prefix and one-hour processing eligibility;
`cleanup_id` immediately retires them, while `deleted_at` is set only on confirmed
object cleanup. Raw originals are not `source_artifacts`. A complete derived VTT
is retained there, and a new ordinary indexing job is created atomically with ASR
completion/raw retirement. Accepted audio frames and actual model duration are
attributed to the ASR job separately from embedding usage; unknown tokens stay null.
An internal source begins as `audio` and becomes `transcript` with explicit
machine-generated/input-kind/profile metadata after adoption. Reindex generations
retain their origin ASR-run FK. The later ADR 0020 API is disabled by default.

The read-only media-inspection slice exposes nullable typed `asr_origin` on managed
sources, transcript pages, evidence and answer/history citations. Source origin
comes from the retained artifact; each published generation's origin comes from
its own `processing_versions.asr_job_id` scoped relationship. Mutable source
metadata is not authoritative. ASR generation can remain 1 while index generations
advance. Ordinary/legacy subtitles have no inferred machine/human-review claim.
No raw input key/digest, window result or credentials are exposed by this projection.

Managed sources also expose nullable `audio_retention` with `processing_expires_at`,
`cleanup_id`, `deleted_at` and status `temporary`, `expired`, `cleanup_pending`,
`cleanup_failed` or `deleted`. Expiry/retirement does not imply physical deletion;
only confirmed cleanup sets `deleted_at`. Existing actor-owned cleanup retry
authorization is unchanged. Inspection required no schema migration; the subsequent
experimental upload also reuses this schema (ADR 0020).
See `sprint4/media-inspection-validation.md` and `sprint4/audio-upload-validation.md`.

### Chat

- `conversations`
- `messages`
- `message_citations`
- `generation_runs`

The local Sprint 3 schema uses immutable `chat_turns` for paired user/assistant
messages and model usage, alongside `conversations` and authoritative
`message_citations`. Retrieval runs retain prompt/retrieval/reranker versions.
Source deletion removes turns containing that source's derived answer text;
project deletion cascades all chat data (ADR 0013).

Citations should reference stable segment/evidence IDs. Store rendered labels separately from the authoritative relationship.

### Curriculum

- `learning_objectives`
- `objective_evidence`
- `coverage_maps`
- `assignments`
- `assignment_versions`
- `assignment_requirements`
- `rubrics`
- `rubric_criteria`

Assignment versions become immutable after the first submission.

### Assessment

- `submissions`
- `submission_files`
- `evaluation_runs`
- `test_results`
- `rubric_results`
- `feedback_items`
- `mastery_events`

Store the exact grading image digest, test bundle version, runner version, and evaluation prompt/model version.

### Scheduling and operations

- `deadlines`
- `reminders`
- `usage_events`
- `model_calls`
- `audit_events`
- `outbox_events`

Use an outbox pattern for important asynchronous transitions so database changes and queued work do not silently diverge.

## Relationship sketch

```text
Tenant
 ├── Membership ── User
 └── Project
      ├── Source
      │    ├── Playlist ── ordered Videos
      │    ├── Processing Jobs
      │    └── Content Segment
      │          ├── Evidence/Frame
      │          └── Embedding
      ├── Conversation
      │    └── Message ── Citation ── Content Segment
      ├── Coverage Map ── Learning Objective ── Evidence
      └── Assignment
           └── Assignment Version
                ├── Requirement/Rubric
                └── Submission
                     └── Evaluation Run
                          ├── Test Results
                          └── Feedback
```

## Initial API surface

Use `/api/v1`. Exact payloads should be generated from Pydantic models and exposed through OpenAPI.

ADR 0018's local WAV/Whisper foundation is a stateless private model boundary,
not a new application endpoint. Its private checkpoint follow-up adds migration
0010 but no public payload. Its subsequent private backend workflow adds internal
registration, original retirement and media jobs (0011/0012), not a public upload
route. The subsequent bounded authenticated API/BFF/form (ADR 0020) reuses that
repository and leaves WAV disabled by default. The original stateless operator
probe creates no project rows; the separate end-to-end probe uses a disposable
project/stack and deletes its own sources, data and objects.

### Stateless visual foundation

ADR 0021's separate visual tool likewise adds no application records, migration or
API. Typed temporary results carry actual PTS, PNG/input hashes, OCR and a versioned
engine/language-data profile. No project-owned frame/OCR is persisted or published
until the later authorized durable video workflow is implemented.

The subsequent private `visual:8091` listener is not part of `/api/v1`: health
returns the requested language's validated processing identity; extraction takes
bounded MP4 bytes plus pinned profile/input digest headers and returns typed
PNG/OCR/timestamps. Both sides validate image/timeline/profile integrity. No user,
tenant, project, source, object URL, prompt or credentials cross this boundary.
It has no public port, persistent storage, migrations, jobs or autonomous retries.
Only a later authorized worker may attach to its isolated internal network.

Migration 0013 adds `visual_runs` and `visual_checkpoint_frames` for the subsequent
private DB component. A complete scope/source/job/generation FK owns each row;
source/project deletion cascades through PNG bytes and OCR. Runs pin actual input
digest/bytes, initiating actor/rights, full identity/profile and a one-hour deadline
from job creation. Complete snapshots retain video/candidate/actual PTS metadata,
frame/text/result hashes and accepted counts. Storage is bounded private staging,
not a published frame/evidence model or final object-store adoption. No API,
registration/dispatcher/task, original-media storage or usage publication is added.

Migration 0018/ADR 0027 later adds nullable bounded `selection_manifest` JSON to
that fully scoped run. v1 remains manifest-free with unchanged canonical bytes/
digests. The new fixed v2 profile/protocol/checkpoint requires all <=600 thumbnail
score/hash records and an exactly recomputable <=20-point selection, matched to
complete actual-PTS frames. Temporal pixel returns are allowed only in v2.
Save/load/gallery integrity checks cover even unselected records; source/project
cascades remove them. Public gallery/evidence/citation origin only extends to the
matching v2 profile/checkpoint version, not scan data. Native service/producer
defaults are not changed by this storage component.

ADR 0028 then connects actual v2 OCR without a schema change. Private
`/health/ready?language=en&selection=change` and `/extract` with the same fixed query
choose v2; old query/default stays uniform. Unknown/duplicate/additional parameters
fail before native work. The trusted worker's `VISUAL_SELECTION` only affects
unpinned jobs; retries restore their saved identity. No public upload parameter.
Both policies use the existing complete manifest/gallery/index/citation/usage/
deletion paths and unchanged native limits.

Migration 0014/ADR 0022 subsequently adds private `video_inputs`, with a full
tenant/project/job/source/generation FK, actor, fixed job-created + one-hour expiry,
bounded input digest/size/language, generated raw key and scoped cleanup FK.
`deleted_at` is set only after confirmed physical deletion. Runs gain `prepared_at`
(requires a saved result); usage gains actual `input_video_bytes` and
`selected_frame_count`. Preparation and usage are atomic and once per logical job;
segment count is zero, local billed amount is zero, unknown model token/time is not
invented. `tutorial.process_video` on the separate visual queue ends at
`visual_prepared`; source remains `metadata_ready` without active generation or
published evidence. The private Python registration repository is not an HTTP API.
Terminal video retry/reprocess requires re-upload; idempotent replay never restores
raw bytes. Final object adoption and product API/UI remain later work.

Migration 0015/ADR 0023 adds `visual_publications`, with composite publication-job/
source/generation and original-visual-run FKs, pinned result digest and atomic
`published_at`. `retained_visual_frames` stores scoped stable ID/ordinal/actual PTS,
PNG geometry, generated object reference/byte digest and literal OCR/text digest.
Each unique candidate has a write-ahead orphan reservation; a committed row is
reused on continuation/retry. Partial rows never appear in public reads.
`publish_visual` command receipts are internal, not an extra public source command;
the API still only accepts retry/cancel/reprocess. `Job.job_type` is now projected
so UI recovery can distinguish derived publication from retired-original extraction.
Derived retry can reuse frames after raw deletion; video reprocess still requires
re-upload. No content_segments/processing_versions/active_generation or fabricated
inference usage is added. Actual copy attempts remain in processing-attempt metrics.

Authenticated no-store `GET /projects/{project_id}/sources/{source_id}/frames`
returns either an honest empty gallery or the whole published manifest with original
job/generation/profile/language/engine origin. It is separate from transcript
browsing and never claims searchable readiness. `GET /projects/{project_id}/frames/
{frame_id}/image` verifies scoped publication and bounded PNG bytes/digest/geometry,
then rechecks access after storage. No object key or raw original is returned.
The corresponding same-origin Next route is a bounded credential-free-browser
proxy, not a signed public object URL. Source/project cascades remove every row;
existing verified prefix cleanup removes adopted and orphan images.

Migration 0016/ADR 0024 adds `visual_index_runs` linked to the full original
publication/source/generation and scoped `visual_index_chunks` for bounded private
embedding batches. Each row retains stable segment/frame, literal character offset,
actual PTS, target vector space and float32 embedding digest. Eight-document groups
resume after loss; only full integrity-checked activation creates evidence/usage.
New internal command receipts use `index_visual`; public source commands remain
retry/cancel/reprocess, with derived-index retry but no public video reprocess.
Superseding an unfinished index removes its private chunks, not published evidence.

`processing_versions.visual_publication_job_id` pins retained-gallery origin;
managed frame segments carry the same FK and a full scoped retained-frame FK.
Legacy validation-only frames remain compatible without a fabricated image/origin.
Frame PTS uses `start_ms=end_ms` (including zero), not an inferred duration;
transcripts still require positive intervals. A scoped public-projection view
supplies nullable `visual_origin` to retrieval, answer/history citations and evidence.
Evidence also projects `frame_id`; missing managed provenance fails closed.
Saved citations remain unchanged across reindexing. Gallery JSON now separately
reports `searchable`, `active_index_generation` and `active_embedding_space`;
index presence does not mean compatibility with the current configured search.
Source inventory exposes that mismatch. Protected evidence reads are no-store
on success and errors. No new public MP4 command/upload endpoint is added.

Migration 0017/ADR 0025 adds opt-in `video_workflows`: full input/job/source/
generation/actor FK, fixed workflow version, immutable configured embedding target
and nullable scoped publication/index job-generation pairs. Source/project
deletion cascades through this metadata. Private `auto_process=True` registration
includes the mode in its request identity; manual registrations keep their old
hash. Preparation plus first child/outbox, and gallery completion plus second
child/outbox, each commit under the same parent fence/final wall-clock check.
Existing source/job DTOs follow the latest generation; no public API field or
video upload route is introduced. Only the original actor may retry derived
automatic work. Archive does not cancel already accepted workflow stages.

ADR 0026 adds no schema/migration. `ManagedSource.video_retention` independently
projects scoped `video_inputs`/cleanup lifecycle fields: `status`,
`processing_expires_at`, nullable `cleanup_id` and `deleted_at`. Expiry is not
confirmed deletion; source generation 2/3 still refers to original generation 1's
raw lifecycle. No key, input digest or private inference payload is exposed.
Authenticated no-store `GET /ingestion/video-capabilities` returns fixed accepted
codec/size/duration/geometry/FPS/frame/language/TTL limits and configured `enabled`,
independent of the existing WAV capability. `POST /projects/{project_id}/sources/video`
accepts exactly file, rights, OCR language, idempotency key and
`retention_acknowledged=accepted`, returning a Registration for the automatic
workflow. The same-origin BFF returns only validated source/job/project IDs and
deduplication state. Public video reprocess remains closed; current derived retry
and protected original cleanup retry retain their initiator fences.

### Projects

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `POST /projects/{project_id}/archive`
- `POST /projects/{project_id}/restore`
- `DELETE /projects/{project_id}`

### Sources

- `GET /ingestion/capabilities` (authenticated, no-store; configured WAV availability
  and fixed limits, not model readiness)
- `POST /projects/{project_id}/sources`
- `POST /projects/{project_id}/sources/uploads`
- `POST /projects/{project_id}/sources/audio` (experimental, opt-in, 202)
- `GET /projects/{project_id}/sources`
- `GET /projects/{project_id}/sources/{source_id}`
- `GET /projects/{project_id}/sources/{source_id}/alignment` (published frame/transcript temporal inspection)
- `GET /projects/{project_id}/sources/{source_id}/descriptions` (configured opt-in, jobs and last complete image-model snapshot)
- `POST /projects/{project_id}/sources/{source_id}/descriptions` (explicit retained-gallery description command, 202)
- `POST /projects/{project_id}/sources/{source_id}/retry`
- `POST /projects/{project_id}/sources/{source_id}/cancel`
- `POST /projects/{project_id}/sources/{source_id}/reprocess`
- `DELETE /projects/{project_id}/sources/{source_id}`
- `GET /projects/{project_id}/jobs/{job_id}`
- `GET /projects/{project_id}/events` for SSE progress

WAV multipart requires `file`, `authorization_mode` (`owner_upload`,
`authorized_upload`, `licensed_content`), `language` (`auto`, `en`, `tr`),
`idempotency_key` (8–128 ASCII letters/digits/underscore/hyphen) and
`retention_acknowledged=accepted`, each exactly once. One optional `playlist_item_id`
UUID selects a current same-scope lesson; absence/empty means standalone. Reject
other or duplicate fields. Authenticate and check `AUDIO_UPLOAD_ENABLED`
before consuming the body; count actual bytes before parsing. The file limit is
20,000,000 bytes, wire limit 20,016,384 bytes, 600-second signed-16 PCM/16 kHz/mono.
The existing 2 MB SRT/VTT endpoint is unchanged. Invalid formats, extra/duplicate
fields, foreign scope and archived projects create no accepted source/job.

The browser uses a separate same-origin `POST /api/projects/{project_id}/sources/audio`
Route Handler, not a larger Server Action. It verifies the capability, input and
upstream project/source/job identities and the requested playlist association; only `{project_id, source_id, job_id,
deduplicated}` reaches the form. Responses are no-store. An interrupted delivery
can already be registered: resend the unchanged file/fields/key or refresh sources.
Changing the draft rotates the key. Local consent is an explicit form requirement,
not a separate persisted legal-consent version or verification of ownership.

Association joins the persisted hash only when nonempty, preserving existing
standalone replay compatibility. Same-key accepted replay is resolved before
current-item validation, so metadata refresh/deletion does not break recovery.
A new upload must target a current available item and cannot replace pending ASR
or indexing. Old source/evidence remains after terminal replacement. UI polling
must not silently change the selected item or key in an uncertain-delivery draft.

Implemented transcript-first contract (ADR 0012): upload/metadata registration
and processing commands return `202` with source/job IDs. Progress uses an
authenticated five-second polling boundary; SSE is not yet implemented. Source
deletion returns a `202` cleanup ticket. Project deletion keeps `204` and returns
`X-Cleanup-ID`/`Location`. `GET /projects/{project_id}/cleanup/{cleanup_id}` remains
authorized after project deletion; `POST` to its `/retry` command restarts failed
cleanup. Old processing versions retain immutable evidence; only the active
generation participates in retrieval. Durable cleanup records survive cascades.

### Temporal evidence inspection

Temporal inspection requires `transcript_source_id`, `assert_same_recording=true`,
an optional integer `offset_ms` in −600000..600000 and either both
`visual_generation`/`transcript_generation` or neither. Unknown/duplicate fields
are rejected. Select only complete published same-tenant/project sources in one
read-only snapshot. Return at most 20 frames with five overlapping transcript
spans each, 4,000-character flagged excerpts, stable evidence IDs and original
processing provenance. Match `start <= actual_frame_pts + offset < end`; never
substitute a nearby cue. Unavailable published inputs return 409, missing/foreign
sources or explicit unpublished generations 404. Success and errors are private,
no-store. No source relationship, content/citation, usage row or schema is created;
the relationship remains `user_asserted`, `semantics_verified=false`. The server
page pins both selected generations before rendering. See `sprint4/timeline-alignment.md`.

### Chat

- `POST /projects/{project_id}/conversations`
- `GET /projects/{project_id}/conversations`
- `GET /projects/{project_id}/conversations/{conversation_id}`
- `POST /projects/{project_id}/conversations/{conversation_id}/messages`
- `GET /projects/{project_id}/conversations/{conversation_id}/stream`
- `POST /projects/{project_id}/citations/{citation_id}/feedback`

Implemented local contract: conversation creation requires a title (defaulted)
and idempotency key. Lists/history are bounded. POST `.../messages` accepts a
self-contained question, optional source IDs and idempotency key, and returns
SSE `start`/`delta`/`complete` after durable validation/commit. GET history provides
recovery; a separate GET stream and citation-feedback command remain outlines,
not implemented endpoints. `GET /projects/{project_id}/evidence/{segment_id}`
returns scoped stable text, timestamps, source and processing generation.
The stateless JSON `/questions` API also accepts optional source IDs.

`GET /projects/{project_id}/sources/{source_id}/transcript` returns published
transcript segments ordered by `(start_ms,end_ms,id)`, never frames or private
checkpoints. The first request selects `active_generation`; subsequent requests
must pin `generation` when `page > 1` (otherwise 422). Each page has at most 50
items with the existing evidence contract, total count/pages, source state and
active versus selected generation. Unknown/deleted/foreign sources, unpublished
generations and nonexistent pages return 404. Pending/metadata sources return an
honest empty first page when no generation is requested. Valid archived projects
and retained older successful generations are readable, independently of configured
embedding space. No model, object-store read, original download or usage event is
needed. Reads use a consistent read-only snapshot without a project write lock.
The 2,000-page browse ceiling covers legacy one-segment/cue validation data;
durable processing remains capped at 10,000 chunks. No ingestion cap is raised.

Optional local generation adds migration 0006 for actual token counts and a model
manifest lookup digest on retrieval/turn records; prompt versions distinguish
model generation from application-side lexical abstention. Unknown usage stays
null. New questions on archived projects are rejected before invoking providers;
saved same-key replay remains readable. Authenticated `GET /api/v1/runtime` reports
only configured mode/model, retrieval baseline and no-paid-provider policy, never
service URLs or credentials. The model port itself is not published.

### Assignments

- `POST /projects/{project_id}/assignments/generate`
- `GET /projects/{project_id}/assignments`
- `GET /projects/{project_id}/assignments/{assignment_id}`
- `PATCH /projects/{project_id}/assignments/{assignment_id}/draft`
- `POST /projects/{project_id}/assignments/{assignment_id}/activate`
- `POST /projects/{project_id}/assignments/{assignment_id}/deadline`
- `POST /projects/{project_id}/assignments/{assignment_id}/hints`

### Submissions

- `POST /projects/{project_id}/assignments/{assignment_id}/submissions`
- `GET /projects/{project_id}/assignments/{assignment_id}/submissions`
- `GET /projects/{project_id}/submissions/{submission_id}`
- `GET /projects/{project_id}/submissions/{submission_id}/evaluation`

### Account data

- `GET /me/usage`
- `POST /me/export`
- `DELETE /me`

## API rules

### Local description schema addition (0019)

`visual_description_runs` pins scoped source/job/generation, original gallery and
actor, expected vision digest/prompt, target embedding space, immutable engine
identity hash, completion and child index. `visual_descriptions` stores each
bounded frame's exact image hash, structured description/hash, reported usage and
latency. All cross-record FKs include tenant/project/source and relevant job/
generation/frame identity; complete source/project deletion cascades these rows.
Private checkpoints are never public evidence. No new object copy is created.

Only full snapshots atomically enqueue existing indexing. `visual_index_runs` and
`processing_versions` optionally pin the description job. The existing origin view
adds nested description identity only for mixed v2 indexes. v1 origin projection
and IDs/text/digests remain unchanged; managed mixed citations require
`extraction_generation < description_generation < index_generation`. Segments use
fixed separate OCR/description prefixes at exact retained-frame PTS, at most 300
1200-character chunks, never a fabricated interval or verified speech claim.
Usage gains prompt/output-token/image-count/image-byte attribution; existing
metrics stay content-free. See `sprint4/frame-descriptions.md` and ADR 0029.

### Boundary rules

- Never derive authorization only from an opaque resource ID; always verify tenant/project membership.
- Prefer command endpoints for meaningful state transitions over unrestricted status patches.
- Use idempotency keys for source creation, assignment generation, uploads, and submissions.
- Return stable machine-readable error codes plus safe user-facing messages.
- Never return raw worker/provider exceptions to the frontend.
- Use signed object URLs with short expiration, content-type restrictions, and size limits.
- Record audit events for destructive, permission-changing, and grading operations.
