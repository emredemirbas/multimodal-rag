# Multimodal Tutorial Learning Workspace

Planning handoff for a product that turns programming video tutorials and playlists into:

- a project-scoped, citation-backed question-answering workspace;
- structured case-study assignments;
- testable code submissions and feedback;
- progress, attempts, and optional deadlines.

The project is in the planning stage. No application scaffold has been created yet.

## Read first

1. [`docs/01-product-brief.md`](docs/01-product-brief.md)
2. [`docs/02-requirements.md`](docs/02-requirements.md)
3. [`docs/03-system-design.md`](docs/03-system-design.md)
4. [`docs/04-sprint-plan.md`](docs/04-sprint-plan.md)
5. [`docs/05-data-model-and-api.md`](docs/05-data-model-and-api.md)
6. [`docs/06-security-and-content-policy.md`](docs/06-security-and-content-policy.md)
7. [`docs/07-open-decisions.md`](docs/07-open-decisions.md)
8. [`docs/08-testing-and-evaluation.md`](docs/08-testing-and-evaluation.md)

Codex should also read [`AGENTS.md`](AGENTS.md) before making changes. A ready-to-paste prompt for a new task is in [`CODEX_KICKOFF.md`](CODEX_KICKOFF.md).

## Proposed first-release boundary

- Programming tutorials, initially Python backend development
- English-language content
- One video or one playlist per source; multiple sources per project
- Uploaded, user-owned, authorized, or appropriately licensed content
- Timestamped transcript plus selected meaningful frames
- Hybrid retrieval with source and timestamp citations
- Generated backend coding case studies
- ZIP/file submission initially; Git integration later
- Deterministic tests plus rubric-grounded AI feedback
- Private single-user projects
- Docker Compose for local development
- Managed model APIs and managed production data services where practical

These are proposed defaults, not silently final decisions. Resolve the blocking items in `docs/07-open-decisions.md` during Sprint 0.

## Core stack

- Frontend: Next.js / React / TypeScript
- API and application services: FastAPI / Python / Pydantic
- Model workflows: LangChain selectively; LangGraph for stateful model-driven workflows
- Database: PostgreSQL with pgvector and PostgreSQL full-text search
- Background work: Celery and Redis
- Object storage: S3-compatible storage; MinIO locally
- Media processing: FFmpeg, scene detection, OCR, and a vision model
- Packaging: Docker and Docker Compose
- Untrusted code: ephemeral OCI images behind a dedicated hardened runner, preferably gVisor or microVM isolation

## Most important constraint

Do not design the product around silently downloading arbitrary public YouTube audiovisual content. Official caption downloads require edit permission, and YouTube policies restrict downloading/caching audiovisual content. Treat YouTube as a metadata/source adapter and provide compliant ingestion modes.

## Intended milestones

- End of Sprint 3: single-video transcript-based cited chat
- End of Sprint 4: playlists and visual-frame understanding
- End of Sprint 6: generated assignments and sandboxed grading
- End of Sprint 9: private beta

