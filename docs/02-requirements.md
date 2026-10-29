# Requirements baseline

This is a baseline for Sprint 0 refinement, not a claim that every detail is final.

The current target is a local GitHub portfolio demonstration with no paid
API/service requirement (ADR 0015). Preserve isolation, safe content handling,
provenance and testing; hosted beta performance/launch targets are deferred.
The owner selected the existing RAG flow as **portfolio v1** on 2026-10-29;
its finite acceptance checklist is in `09-delivery-status.md`. Assignment,
submission, grading and tutoring requirements below remain post-v1 roadmap.
Experimental media/model capabilities do not imply full Alpha 2 quality approval.

## Functional requirements

### Accounts and projects

- Users can authenticate and manage private projects.
- Users can create, rename, archive, restore, and delete projects.
- A project contains sources, chat, assignments, submissions, and progress.
- All access is authorized by tenant and project membership.
- Deleting a project deletes or schedules deletion of all derived data.

### Sources and ingestion

- A project can contain an individual video, a playlist, supporting documents, or uploaded transcript/media.
- Source adapters expose a common normalized contract.
- The system validates source ownership/authorization/license mode before processing.
- Playlist metadata is enumerated without assuming audiovisual download rights.
- Long operations run asynchronously with visible state and progress.
- Jobs are idempotent, retryable, cancelable, and resumable.
- Transcript segments retain precise start/end timestamps.
- Processing versions are recorded so sources can be reprocessed safely.

Suggested source lifecycle:

```text
created → validating → metadata_ready → processing → indexing → ready
             └───────────────────────────────→ failed
Any nonterminal state → cancelled
ready → reprocessing → ready
```

### Multimodal representation

- Select frames using scene changes, OCR novelty, and visual difference rather than fixed intervals alone.
- Deduplicate nearly identical frames.
- Extract OCR and a structured visual description.
- Align frames with transcript spans and timestamps.
- Retain the original frame only when storage is permitted.
- Preserve modality and provenance on every indexed segment.
- A visual answer can show or link to the supporting frame and timestamp.

### Retrieval and chat

- Search combines PostgreSQL full-text search and semantic vector search.
- Retrieval is filtered by tenant, project, source status, and permissions.
- Exact names, code identifiers, error messages, and commands remain searchable.
- Results are fused and reranked before context construction.
- Answers distinguish tutorial evidence from external documentation.
- Tutorial citations link to the source and timestamp.
- Unsupported questions receive an explicit limitation or abstention.
- Chat streams responses and persists conversation history.
- Retrieval and generation record model, prompt, and index versions.

### Learning objectives and assignments

- The system derives a versioned coverage map from project sources.
- Users can specify experience, difficulty, and available time.
- Assignments are generated into a strict Pydantic schema.
- Assignments are editable drafts before activation.
- Every requirement is labeled `covered`, `prerequisite`, or `extension`.
- Covered requirements cite project sources.
- External requirements cite allowlisted, version-aware official documentation.
- Assignment versions are immutable after a learner submits against them.

Minimum assignment fields:

- title and scenario;
- learning objectives;
- prerequisites;
- estimated effort;
- functional requirements and constraints;
- deliverables;
- acceptance criteria;
- evaluation rubric;
- hints;
- tutorial citations;
- supplementary citations;
- deadline and timezone.

### Submissions and feedback

- A learner can upload a supported file/archive submission.
- Submission artifacts are immutable and versioned.
- Untrusted code runs only through the dedicated sandbox service.
- Objective pass/fail results come from deterministic checks.
- Qualitative rubric feedback is structured and evidence based.
- LLM feedback cannot overwrite deterministic test outcomes.
- Learners can review logs safe for disclosure, request hints, and resubmit.
- The system retains evaluation provenance and attempt history.

### Deadlines and progress

- Deadlines are optional and stored in UTC with the learner's timezone.
- Beta reminders are in-app.
- Grace periods and extension behavior are explicit.
- Progress is derived from completed actions and evaluation evidence.
- Hints use progressive disclosure.

## Non-functional requirements

### Security and privacy

- No cross-project or cross-tenant data exposure.
- Source URLs are parsed and allowlisted; arbitrary server-side URL fetching is prohibited.
- Transcripts, documents, OCR, and submissions are treated as untrusted input.
- Secrets never enter frontend bundles, source artifacts, prompts, or sandboxes.
- Complete user/project deletion is auditable.
- Sensitive logs are redacted.

### Reliability

- At-least-once jobs do not create duplicate logical artifacts.
- Worker crashes are recoverable.
- Individual playlist-item failures do not fail the whole playlist.
- External provider calls use timeouts, bounded retries, and failure classification.
- Database and object-store backups have a tested restoration procedure before beta.

### Performance targets for beta

- Initial chat response begins in roughly five seconds under normal load.
- Project pages remain usable while sources process.
- A 10-video playlist is processed asynchronously with per-video progress.
- Limits are enforced by user, project, source duration, job concurrency, and provider spend.

### Accessibility and UX

- Keyboard navigation and visible focus states
- Accessible labels and status announcements
- Clear loading, empty, partial-failure, and recovery states
- Transcript and citation access without relying only on images
- Mobile-responsive web layout, without a native mobile application

### Maintainability

- Typed API contracts
- Database migrations
- Structured logs and traces
- Application-owned model interfaces
- Prompt and processing versioning
- Automated unit, integration, isolation, and evaluation tests
