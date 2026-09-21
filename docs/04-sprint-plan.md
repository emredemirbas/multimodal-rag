# Sprint plan

## Estimation assumptions

- Team: three full-time engineers covering frontend, backend, and AI/platform
- Cadence: two-week sprints, except Sprint 0 (one week) and sandboxing Sprint 6 (three weeks)
- Private beta: approximately 20 calendar weeks
- Solo full-time developer: approximately 32–40 weeks
- Self-hosted foundation models or a custom microVM platform may add 4–8 weeks

## Milestones

| Milestone | End | Outcome |
|---|---:|---|
| Architecture validated | Sprint 0 | Content path, cost, and core technical risks validated |
| Alpha 1 | Sprint 3 | Single-video transcript RAG with citations |
| Alpha 2 | Sprint 4 | Playlist and frame-aware retrieval |
| Alpha 3 | Sprint 6 | Case studies, submissions, and grading |
| Private beta | Sprint 9 | Secure, monitored end-to-end product |

## Sprint 0 — Product and technical validation

**Duration:** 1 week

Deliver:

- confirmed persona and domain;
- supported content modes and retention policy;
- selected submission/grading path;
- cost estimate per processed hour and 10-hour playlist;
- UX wireframes;
- Dockerfiles and a minimal Compose proof of concept;
- technical spike: one supported tutorial → timestamped transcript → selected frames → one cited answer;
- architecture decision records.

Exit:

- at least one compliant ingestion path works end-to-end;
- no dependency on arbitrary public-video downloading;
- blocking decision log is resolved or explicitly accepted as risk;
- basic cost and latency data exist.

## Sprint 1 — Foundation and projects

**Duration:** 2 weeks

Deliver:

- Next.js shell and FastAPI application;
- PostgreSQL migrations and authentication;
- project CRUD and navigation;
- base source/job schema;
- Docker Compose for frontend, API, Postgres/pgvector, Redis, and MinIO;
- health checks, CI, configuration, and initial tests.

Exit:

- project create/rename/archive/delete works;
- project isolation tests pass;
- development environment starts reproducibly;
- deployable development images are built in CI.

## Sprint 2 — Transcript-first ingestion

**Duration:** 2 weeks

Deliver:

- normalized source-adapter contract;
- individual video and playlist metadata adapters;
- uploaded transcript/subtitle and permitted media paths;
- Celery/Redis jobs;
- timestamp normalization and semantic chunking;
- idempotency, retry, cancellation, reprocessing, and progress UI;
- dedicated ingestion-worker image.

Exit:

- one supported video becomes timestamped indexed segments;
- retry does not duplicate logical artifacts;
- errors are actionable and deletion cleans derived data.

## Sprint 3 — Project-scoped RAG and chat

**Duration:** 2 weeks

Deliver:

- text embeddings and exact vector search;
- PostgreSQL full-text search;
- rank fusion and reranking;
- project/source filters;
- streaming chat and persistence;
- timestamp citations and jump-to-source behavior;
- abstention behavior;
- initial labeled evaluation set.

Exit:

- benchmark questions retrieve and cite correct evidence at an agreed threshold;
- no cross-project leakage in negative tests;
- users can inspect every cited source segment.

## Sprint 4 — Playlists and multimodal evidence

**Duration:** 2 weeks

Deliver:

- full playlist import and ordered video relationships;
- bounded per-video concurrency and resumability;
- FFmpeg/media-worker image;
- scene/change detection, deduplication, OCR, and vision descriptions;
- transcript/frame alignment;
- frame-aware retrieval and citations.

Exit:

- a 10-video playlist can process, partially fail, and resume;
- visual benchmark questions retrieve relevant frames;
- duplicate frames are suppressed.

## Sprint 5 — Learning model and case studies

**Duration:** 2 weeks

Deliver:

- learning objectives and coverage maps;
- learner profile;
- strict assignment schema;
- LangGraph generation/validation/revision workflow;
- official-document allowlist, provenance, and version metadata;
- editable and versioned assignment drafts;
- `covered`, `prerequisite`, and `extension` labels.

Exit:

- assignments are schema-valid, traceable, and editable;
- covered requirements have tutorial evidence;
- extension material has separate official citations;
- a reviewed sample set passes quality criteria.

## Sprint 6 — Submission and sandboxed grading

**Duration:** 3 weeks

Deliver:

- immutable file/archive submissions;
- dedicated assessment coordinator and sandbox runner;
- language-specific OCI grading images;
- gVisor, microVM, or equivalent hardened isolation;
- no network by default, read-only base filesystem, non-root user, capability removal, and resource limits;
- visible/hidden tests, lint/type checks, rubric evaluation, feedback, and resubmission.

Exit:

- sandbox escape/threat tests satisfy the agreed security review;
- tests are reproducible;
- deterministic results cannot be overwritten by LLM output;
- full submit → feedback → resubmit flow works.

## Sprint 7 — Deadlines, tutoring, progress, and UX

**Duration:** 2 weeks

Deliver:

- timezone-aware optional deadlines;
- in-app reminders;
- assignment lifecycle and progress dashboard;
- progressive hint workflow;
- learner mastery events;
- polished responsive workspace and evidence viewer.

Exit:

- deadlines are correct across timezones;
- progress is evidence-based;
- tutor uses assignment and attempt history without prematurely revealing solutions;
- key flows pass accessibility checks.

## Sprint 8 — Security, reliability, and observability

**Duration:** 2 weeks

Deliver:

- row-level security where appropriate;
- prompt-injection and SSRF defenses;
- quotas and cost attribution;
- deletion/export workflows;
- logs, metrics, traces, model-call telemetry, and operational dashboards;
- backups and restore test;
- image scanning, SBOMs, pinned images, and runtime hardening;
- load, chaos, and failure-recovery tests.

Exit:

- no critical isolation findings;
- project deletion covers all stores;
- expensive calls are attributable;
- worker and provider failures recover predictably;
- restore procedure has been exercised.

## Sprint 9 — Private beta

**Duration:** 2 weeks

Deliver:

- onboarding and sample project;
- user feedback capture;
- admin/support view;
- product, retrieval, assignment, and cost dashboards;
- beta documentation, runbooks, bug fixes, and tuning.

Exit:

- 20–50 invited users can complete the full learning loop;
- critical failures are observable and recoverable;
- funnel data reveals where users abandon the workflow;
- known limitations are visible to users.

