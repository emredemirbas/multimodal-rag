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

ADR 0021 adds a separately invoked, no-network `visual-inspect` container, not an
application worker or upload capability. Its bounded FFprobe/FFmpeg/Tesseract
children inherit the kernel network filter and have no application credentials or
mounts. Temporary originals/intermediates stay in container tmpfs; the typed
interface returns actual PTS, image/input hashes, local OCR and engine/language-data
profile. Uniform candidates/exact-pixel deduplication are not scene detection.
The CLI prints content-free summaries only. Durable scoped video jobs, raw cleanup,
derived storage, UI and visual citations remain follow-up. Normal startup does not
run it; explicit image build includes small public Debian OCR-language assets, not
Ollama/Whisper downloads. See `sprint4/local-visual-guide.md`.

The private-service follow-up adds optional `visual` on `visual-private` only
(`local-visual` profile, no host ports/mounts/app credentials). It binds a listener
before denying new sockets/connect, verifies inheritance in a fresh child, and
serves bounded stateless MP4 requests with the same isolated parser. A worker-side
HTTP client requires a pinned processing identity and validates input digest,
actual PTS and bounded PNG/OCR integrity; it has no proxy/redirect/retry/fallback.
The API/ordinary/audio workers never join that network. The later dedicated
trusted visual worker below is its sole application-side peer.
See `sprint4/visual-service-plan.md`; the listener alone adds no upload capability.

The subsequent checkpoint component (migration 0013) pins video bytes, actor,
rights and processing identity under the existing scoped job fence. It saves one
complete validated PNG/OCR batch atomically in bounded private PostgreSQL staging
(<=20 frames/12 MB image bytes), outside published evidence and final object
storage. A retry can read that snapshot rather than repeat a completed extraction;
an interrupted in-flight native call can still repeat in full. Membership remains
locked through the transaction; wall-clock lease/one-hour job-creation eligibility
is rechecked before commit. Source/project deletion cascades through all staged
bytes/text. This is not video registration, an executable queue, original cleanup
or visual RAG. The native image explicitly excludes checkpoint/database code.
See `sprint4/visual-checkpoints-plan.md`.

ADR 0022/migration 0014 connects private registration, S3 temporary originals,
outbox delivery and a separate `visual-worker`/queue to those checkpoints. Only
this trusted credential-bearing coordinator joins both app and visual-private
networks; FFmpeg/Tesseract still runs solely in the credential-free native service.
Visual task limits are 180/210 seconds, DB lease 240 and configured visibility 300;
other workers keep their existing limits. A complete checkpoint resumes without
provider construction or raw GET. Atomic completion records actual accepted usage
counts, marks `visual_prepared` / source `metadata_ready` and schedules raw cleanup.
Eligibility is fixed at job creation + one hour; success/cancel/permanent failure/
expiry/revocation retire raw input. Independently verified deletion remains retryable
and observable. Private prepared bytes are not active retrieval/evidence: object
adoption, visual indexing/citations and public upload/UI remain follow-up. See
`sprint4/video-worker-plan.md`; default Compose startup remains unchanged.

ADR 0023/migration 0015 supplies the retained-frame inspection slice. An internal
authorized command creates a new derived-publication job linked to the immutable
prepared extraction; it never consumes the raw input again. The same trusted
visual worker adopts one PNG per delivery using unique orphan reservations and
post-PUT actor/lease fencing. Atomic gallery publication requires the complete
validated manifest. `retained_visual_frames` links stable IDs/PTS/OCR/object hashes
to the exact original visual run and publication generation. Partial objects stay
private. Source status remains `metadata_ready` without active retrieval generation.
Scoped gallery/PNG reads and a bounded server-only no-store image proxy provide
inspection with unreviewed-OCR/capability caveats. Complete source/project deletion
still covers raw, orphan and adopted images/rows. Indexing/citations and product
MP4 upload are separate follow-ups; see `sprint4/visual-gallery-plan.md`.

ADR 0024/migration 0016 adds that retained-OCR index continuation. An internal
authorized command pins one published gallery and immutable embedding space in a
new `visual_index` job/generation. Ordinary ingestion performs text-only embeddings,
eight literal chunks per checkpoint and at most eight batches per bounded delivery.
Private staging never participates in search; validated complete promotion activates
frame evidence/usage atomically. Each chunk keeps frame, literal offset, actual
point PTS and processing version. Scoped version/gallery/frame FKs and a public-only
origin view retain the original extraction, including saved chat after reindexing.
Gallery state reports active index generation/space separately. Model context is
unreviewed OCR, not image understanding. No raw/native access, original extension,
public MP4 upload or new provider. See `sprint4/visual-index-plan.md`.

ADR 0025/migration 0017 links these existing stages only for explicit private
automatic registrations. PostgreSQL stores original actor/input/policy/embedding
target and scoped child job identities. Successful parent completion and child
job/outbox creation share a transaction and final wall-clock fence. The visual
worker cannot substitute its own embedding default. Accepted work continues
through archival; cancellation/revocation stops progression, and only the original
initiator may retry derived work. This is ordinary durable job coordination, not
a LangGraph flow. Existing manual mode and public upload gates stay unchanged.
See `sprint4/video-workflow-plan.md`.

ADR 0026 exposes the accepted standalone workflow through a separate default-off
MP4 multipart API/BFF/form. Native decoding remains exclusively in the isolated
service; authenticated actual-byte/time/part bounds precede parsing. API and BFF
each admit one video delivery per process without queuing large bodies. Only API
tmpfs capacity grows to 256 MiB so its existing multipart spool can fit 100 MB;
subtitle/chat/WAV limits do not change. Source inventory's typed video-original
projection tracks expiry vs retirement vs confirmed cleanup across generations;
the accessible UI continues polling after indexing. Configuration is not native
readiness/quality; original-video playback/audio/playlist association are absent.

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
claim ASR jobs. Queue routing/worker and original cleanup were that component's
follow-up, implemented by the next private backend slice below.

The next private backend slice (ADR 0019) implements that dedicated media worker,
fixed outbox routing and temporary-original lifecycle. One validated window per
delivery checkpoints progress and requeues without a failure attempt. Complete
VTT adoption uses a unique reserved object prefix and a post-PUT authorization
fence; ASR completion, provenance/usage, indexing-job creation and raw retirement
commit together. Original eligibility expires after one hour; the scheduler
observably retries physical cleanup. Public WAV upload remains disabled.

The read-only inspection follow-up exposes typed ASR origin and original-audio
retention state without inference or object access. Artifact links identify source
origin; processing-version links identify evidence/citation origin even after
reindexing. Mutable metadata never decides a machine-generated label. The UI
separates expiry/retirement from confirmed physical deletion, follows cleanup after
index completion and uses the existing authorized failed-cleanup retry boundary.
The subsequent experimental upload boundary (ADR 0020) connects that workflow:
authenticated `GET /api/v1/ingestion/capabilities` plus multipart
`POST /api/v1/projects/{project_id}/sources/audio`, with a separate same-origin
browser Route Handler and gated form. `AUDIO_UPLOAD_ENABLED=false` by default;
capability means configured availability, not model health. Audio wire reads are
bounded before multipart parsing (20 MB + 16 KiB, 30 seconds); API authentication
and flag checks precede body consumption. The BFF validates fields and returns
only a scoped receipt. Actual PCM/duration validation remains in the repository.
No inline ASR, subtitle/chat limit increase or schema change. Native verification
and its recognition-quality limitations are recorded separately in
`sprint4/audio-upload-validation.md`.

The WAV/playlist follow-up reuses the existing scoped item/parent relationships.
Registration binds an optional current lesson atomically with the audio source,
ASR job and outbox, preserving audio metadata and original association provenance.
ASR and ordinary indexing claims share one project-locked per-playlist live-lease
cap; every worker receives the same configuration. Slot waiting keeps bounded
retry semantics and does not extend original eligibility. BFF receipts verify
the selected item while uncertain-delivery drafts survive snapshot changes.
No migration, new provider, format or default enablement; see ADR 0014's follow-up.

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

The sandbox runner belongs in a separate hardened environment. Optional model
APIs run in local isolated services under the selected free local scope (ADR 0015).

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

The internal curriculum JSON adapter is now separate from chat answers. It requires
an explicit local `qwen3:4b` digest/engine pin, checks identity before and after
inference and returns bounded raw JSON plus usage to the application. A scoped
call receipt commits before inference; no database lock spans the HTTP request.
Exact request-body hashes and schema/request versions complement the existing
prompt/model metadata. `TutorialAssignmentWorkflow` now uses pinned LangGraph
1.2.18 internally for model -> deterministic validation -> checkpoint/publication
transitions. It extracts objectives from lossless bounded source batches, selects
a small goal subset, generates and allows at most one revision. Each delivery
does at most one physical model call; accepted progress remains in the existing
tenant/project-owned run checkpoints. No library checkpointer or hosted tracing
is used (tracing is explicitly disabled even if enabled in the environment).
The default registry/public producer remain closed pending native-output review
and approved document capture. The owner selected optional external topics with
approval for each official document. Queue coordination and CRUD stay ordinary code.

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
