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

### Projects

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `POST /projects/{project_id}/archive`
- `POST /projects/{project_id}/restore`
- `DELETE /projects/{project_id}`

### Sources

- `POST /projects/{project_id}/sources`
- `POST /projects/{project_id}/sources/uploads`
- `GET /projects/{project_id}/sources`
- `GET /projects/{project_id}/sources/{source_id}`
- `POST /projects/{project_id}/sources/{source_id}/retry`
- `POST /projects/{project_id}/sources/{source_id}/cancel`
- `POST /projects/{project_id}/sources/{source_id}/reprocess`
- `DELETE /projects/{project_id}/sources/{source_id}`
- `GET /projects/{project_id}/jobs/{job_id}`
- `GET /projects/{project_id}/events` for SSE progress

Implemented transcript-first contract (ADR 0012): upload/metadata registration
and processing commands return `202` with source/job IDs. Progress uses an
authenticated five-second polling boundary; SSE is not yet implemented. Source
deletion returns a `202` cleanup ticket. Project deletion keeps `204` and returns
`X-Cleanup-ID`/`Location`. `GET /projects/{project_id}/cleanup/{cleanup_id}` remains
authorized after project deletion; `POST` to its `/retry` command restarts failed
cleanup. Old processing versions retain immutable evidence; only the active
generation participates in retrieval. Durable cleanup records survive cascades.

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

- Never derive authorization only from an opaque resource ID; always verify tenant/project membership.
- Prefer command endpoints for meaningful state transitions over unrestricted status patches.
- Use idempotency keys for source creation, assignment generation, uploads, and submissions.
- Return stable machine-readable error codes plus safe user-facing messages.
- Never return raw worker/provider exceptions to the frontend.
- Use signed object URLs with short expiration, content-type restrictions, and size limits.
- Record audit events for destructive, permission-changing, and grading operations.
