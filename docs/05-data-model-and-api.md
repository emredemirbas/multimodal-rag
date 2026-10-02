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

### Chat

- `conversations`
- `messages`
- `message_citations`
- `generation_runs`

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
- `DELETE /projects/{project_id}/sources/{source_id}`
- `GET /projects/{project_id}/jobs/{job_id}`
- `GET /projects/{project_id}/events` for SSE progress

### Chat

- `POST /projects/{project_id}/conversations`
- `GET /projects/{project_id}/conversations`
- `GET /projects/{project_id}/conversations/{conversation_id}`
- `POST /projects/{project_id}/conversations/{conversation_id}/messages`
- `GET /projects/{project_id}/conversations/{conversation_id}/stream`
- `POST /projects/{project_id}/citations/{citation_id}/feedback`

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
