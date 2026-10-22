# Proposed system design

Current target: free local portfolio mode (ADR 0015), superseding the managed
model/hosted beta deployment default. Optional Ollama runs as a separate local
process/container; default offline demos and CI require no model download.

Optional semantic retrieval uses Qwen3 Embedding 0.6B behind the same local-only
boundary (ADR 0016). Index identity includes approved manifest, 1024 dimensions
and query-template version. Document embeddings run in the ingestion process;
queries are bounded API requests. Incompatible active generations are excluded
before distance calculation, not silently blended into either retrieval channel.
The production evolution sections remain future considerations, not current work.

Resumable indexing (ADR 0017) stages semantic batches under the existing job lease.
The scheduler/outbox continues bounded deliveries without consuming failure
retries. No staging row participates in retrieval or citation inspection; the
full generation is promoted atomically. LangGraph is not involved in queue work.

Published transcript browsing is a separate read-only source/evidence boundary.
Fixed chronological pages pin a successful processing generation and never read
private staging or invoke models. Each request uses one repeatable-read snapshot;
reprocessing cannot mix generations across pages. The scoped timeline index in
migration 0009 accelerates this navigation without changing vector search.

ADR 0018 adds an optional private, stateless ASR foundation for the approved WAV
scope. It has no application credentials or published port, and denies new sockets/
outbound connect after binding its listener. Fresh resource-bounded filtered child
processes receive <=30s PCM only. Model downloads are explicit and weights are
read-only during inference. This foundation is not yet a media queue/ingestion
workflow: no audio upload, raw retention, partial index or new database record is
enabled until the dedicated worker/cleanup follow-up is complete.

The first durable follow-up is private ASR window staging (migration 0010).
It pins input/model/language/assembly identity, fences each operation using the
existing job lease and actor/project scope, and assembles only complete validated
windows into an immutable VTT. It does not call a model, adopt an object, activate
evidence or create an application audio job. Ordinary ingestion workers do not
claim ASR jobs; queue routing/worker and original cleanup remain follow-up work.

## Architecture style

Start as a modular monolith with separate runtime processes. This preserves clear module boundaries without incurring early microservice coordination costs.

Separate processes/services are justified for:

- frontend;
- FastAPI application;
- ingestion/media workers;
- scheduler;
- sandbox runner;
- PostgreSQL;
- Redis;
- object storage.

## High-level architecture

```text
┌───────────────────────────────────────────────────────────────────┐
│ Next.js web application                                          │
│ Projects │ Sources │ Chat │ Evidence viewer │ Assignment │ Results│
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTPS + SSE
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│ FastAPI modular application                                      │
│ Auth │ Projects │ Sources │ Chat │ Assignments │ Submissions      │
│ Progress │ Usage/quotas │ Admin/support                           │
└────────────┬──────────────────┬────────────────────┬───────────────┘
             │                  │                    │
             ▼                  ▼                    ▼
┌────────────────────┐ ┌────────────────┐ ┌─────────────────────────┐
│ PostgreSQL         │ │ Redis          │ │ S3-compatible storage   │
│ Relational state   │ │ Celery broker  │ │ Permitted source data   │
│ Full-text search   │ │ Cache/locks    │ │ Frames, submissions     │
│ pgvector           │ │ Rate state     │ │ Generated artifacts     │
│ RLS/audit data     │ └───────┬────────┘ └─────────────────────────┘
└────────────────────┘         │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│ Worker processes                                                  │
│ Validate │ Metadata │ ASR │ Scenes │ OCR │ Vision │ Chunk │ Embed │
└──────────────────────────────┬────────────────────────────────────┘
                               │
             ┌─────────────────┴──────────────────┐
             ▼                                    ▼
┌────────────────────────────┐       ┌───────────────────────────────┐
│ Model gateway              │       │ Assessment boundary           │
│ LLM / embed / vision       │       │ Coordinator → hardened runner │
│ reranker / transcription   │       │ → ephemeral sandbox           │
└────────────────────────────┘       └───────────────────────────────┘
```

## Container layout

Local Docker Compose:

```text
frontend
api
ingestion-worker
media-worker
scheduler
postgres-pgvector
redis
minio
```

The sandbox runner belongs in a separate hardened environment. Model APIs are external initially.

Production should build immutable images for the frontend, API, workers, and scheduler. Prefer managed PostgreSQL, Redis, and object storage. A managed container platform is sufficient for beta; Kubernetes is not required.

## Component responsibilities

### Web application

- project navigation and settings;
- source ingestion and progress;
- streaming chat;
- synchronized video/frame/transcript evidence viewer;
- assignment editor and workspace;
- submission and feedback history;
- progress and deadlines.

### FastAPI application

- authentication/authorization boundary;
- transactionally consistent application commands;
- project/source/chat/assignment APIs;
- signed object upload/download URLs;
- SSE streaming and job-status endpoints;
- usage and quota enforcement;
- creation of background jobs, never heavy processing itself.

### Worker layer

- source validation and normalized metadata;
- permitted transcription or transcript parsing;
- scene detection and frame selection;
- OCR and frame descriptions;
- timeline alignment and semantic segmentation;
- embeddings and index writes;
- document parsing;
- cleanup and reprocessing.

### Model gateway

Expose application-owned interfaces for:

- chat completion;
- structured generation;
- text embeddings;
- optional visual embeddings;
- frame understanding;
- transcription;
- reranking.

Record provider, model identifier, prompt/template version, latency, tokens, and cost attribution. Provider payloads should not leak into domain models.

### LangGraph workflows

Appropriate uses:

- objective extraction → assignment generation → validation → revision → approval;
- tutor decision between retrieval, a guiding question, a hint, or evaluation evidence;
- structured qualitative rubric evaluation;
- learner-state updates that require explicit transitions.

Inappropriate uses:

- HTTP CRUD;
- Celery job scheduling;
- simple parsing or embedding loops;
- ordinary database transactions.

## Ingestion flow

```text
Register source
  → validate source type, rights mode, quota, and canonical ID
  → fetch permitted metadata
  → expand playlist into ordered video records
  → acquire/parse supported transcript or media input
  → normalize timestamps and text
  → detect scenes and meaningful visual changes when media is permitted
  → OCR and describe selected frames
  → align transcript, frame, and topic timeline
  → create semantic learning segments
  → embed/index transactionally
  → run retrieval smoke checks
  → mark source ready
```

Every stage must have an idempotency key and a processing version. Store raw provider responses only when necessary and permitted.

## Multimodal representation

Initial approach:

1. Turn frame OCR and structured descriptions into searchable text.
2. Store modality, frame timestamp, and object reference with the segment.
3. Retrieve through the text/hybrid pipeline.
4. When visual evidence is selected, give the original permitted frame to a vision-capable generator.

This is simpler than maintaining a separate image-vector system while still allowing visual evidence to affect retrieval and generation. A later experiment can compare true image embeddings against this baseline.

## Retrieval and answer flow

```text
Question
  → authorize tenant/project
  → classify intent and required modalities
  → full-text retrieval for exact/code terms
  → vector retrieval for semantic similarity
  → fuse ranks and deduplicate
  → rerank
  → enforce evidence diversity and context budget
  → construct provenance-rich context
  → generate or abstain
  → validate citations against retrieved segment IDs
  → stream answer
```

Begin with exact vector search under strict project filters. Evaluate HNSW later. Project-scale corpora are likely small enough that predictable recall matters more than premature approximate indexing.

## Assignment and grading flow

```text
Coverage map + learner profile
  → select objectives and difficulty
  → generate structured assignment draft
  → validate completeness, scope, sources, and solvability
  → revise when invalid
  → user reviews/activates immutable version
  → learner submits immutable artifact
  → validate file type/size
  → execute deterministic checks in hardened sandbox
  → apply structured qualitative rubric
  → generate evidence-grounded explanation and hints
  → store evaluation and mastery events
```

## Project isolation

- Include `tenant_id` and `project_id` on project-owned tables.
- Apply both in every repository/query method.
- Use PostgreSQL row-level security as defense in depth where appropriate.
- Put objects under tenant/project/source prefixes and issue short-lived signed URLs.
- Validate citations belong to the active project before rendering.
- Include negative isolation tests for REST, background jobs, retrieval, chat, and object access.

## Deployment evolution

Beta:

- Docker Compose locally;
- managed container service in production;
- managed Postgres/Redis/object storage;
- autoscaled CPU workers where useful;
- dedicated isolated sandbox hosts;
- external managed model APIs.

Scale only after measurements:

- split media workers by CPU/GPU profile;
- partition large vector indexes;
- add HNSW and iterative scans;
- introduce separate retrieval service only when load requires it;
- introduce Kubernetes only for a demonstrated orchestration need.
