# Project instructions for Codex

## Before implementation

Read all files in `docs/`, starting with `01-product-brief.md` and `07-open-decisions.md`. Treat these documents as the product baseline. If a user instruction conflicts with them, follow the user and update the relevant document so the repository remains internally consistent.

The repository currently contains a planning handoff, not a finished specification. Do not silently decide a blocking product question. Surface material assumptions in the plan.

## README style

Keep README.md focused on the product: what it does, installation, usage,
architecture, limitations, development and documentation links. Keep sprint
details, delivery/completion claims, portfolio milestones, CI run/commit records,
test counts and internal handoff instructions in docs/, not in the public README.

## Delivery approach

- Build a modular monolith first, with separate processes for web, API, background workers, scheduler, and sandbox runner.
- Work sprint by sprint. Do not implement later-sprint features merely because a library makes them easy.
- Keep changes small, tested, and documented.
- Add database migrations for schema changes.
- Add observability and usage attribution as features are introduced, not only at the end.
- Every project-owned record and query must enforce both tenant and project scope.
- Preserve evidence provenance: answers and assignments must point to stable source segments and processing versions.

## Architecture constraints

- Use FastAPI/Pydantic for the Python API boundary.
- Use PostgreSQL for application state, full-text search, and pgvector.
- Begin with exact, project-filtered vector search. Add HNSW only after benchmarks show a need.
- Use a real job system for media/ASR/OCR/embedding work; do not use in-process FastAPI background tasks for heavy jobs.
- Use LangGraph only for model-driven stateful workflows such as assignment generation/validation and tutoring. Do not use it as a replacement for the job queue or ordinary CRUD.
- Keep model providers behind application-owned interfaces and persist model/prompt/version metadata.
- Use Docker Compose for local services. Production may use a managed container platform; Kubernetes is not an MVP requirement.
- Do not expose the Docker socket to the API or ordinary workers.
- Ordinary Docker containers are not the sole security boundary for untrusted code. Route submissions through a dedicated runner with gVisor, a microVM, or an equivalent isolation layer.

## Content and safety constraints

- Do not add unofficial arbitrary-video downloading as the product's required ingestion path.
- Supported inputs should be user-uploaded, user-owned, explicitly authorized, or appropriately licensed.
- Validate source URLs against an allowlist; never let workers fetch arbitrary user-supplied URLs.
- Treat transcripts, documents, OCR, frames, and submissions as untrusted input.
- Disable sandbox networking by default and apply strict time, CPU, memory, disk, PID, and filesystem limits.
- Keep secrets out of images, repositories, frontend bundles, prompts, logs, and sandbox environments.
- Implement complete project deletion across relational data, embeddings, objects, and derived artifacts.

## Product behavior

- Separate tutorial-covered material from prerequisites and extensions.
- Cite tutorial evidence with video and timestamps.
- Label external documentation separately and retain its URL and version/retrieval date.
- Prefer abstaining over presenting unsupported claims as tutorial content.
- Deterministic tests decide objective pass/fail conditions. LLMs explain results and apply qualitative rubrics; they do not override test outcomes.
- Hints should be progressive and should not reveal the full solution immediately.

## Definition of done

A feature is not done until it has:

- tests proportional to its risk;
- authorization and project-isolation coverage;
- failure and retry behavior where relevant;
- useful logs/metrics without sensitive data;
- database migrations where relevant;
- documentation for material architectural or product changes;
- accessible loading, empty, error, and success states in the UI.
