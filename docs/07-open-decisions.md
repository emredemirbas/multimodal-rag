# Open decisions and proposed defaults

Resolve the blocking section during Sprint 0. Replace `Proposed` with `Confirmed` or record the selected alternative and rationale.

## Blocking before broad implementation

| Decision | Proposed default | Status |
|---|---|---|
| Initial audience | Intermediate Python developers | Confirmed for MVP, 2026-09-21 |
| Initial subject scope | FastAPI, Pydantic, SQL, API testing | Confirmed for MVP, 2026-09-21 |
| Supported source rights | Uploaded, owned, authorized, or appropriately licensed | Confirmed for MVP, 2026-09-21 |
| Public YouTube URL behavior | Import metadata; require a supported transcript/media path | Confirmed for MVP, 2026-09-21 |
| Primary submission | ZIP/file upload | Confirmed for MVP, 2026-09-21 |
| Grading languages | Python only | Confirmed for MVP, 2026-09-21 |
| Grading method | Deterministic tests plus qualitative rubric feedback | Confirmed for MVP, 2026-09-21 |
| Original media retention | Avoid by default; store only permitted derived artifacts | Confirmed for MVP, 2026-09-21 |
| Model strategy | Keyless demo plus optional local models behind provider-neutral interfaces | Confirmed for free portfolio mode, 2026-10-11; supersedes managed-API default (ADR 0015) |
| Initial tenancy | Private single-user projects | Confirmed for MVP, 2026-09-21 |
| Sprint 1 identity boundary | Application-owned adapter; local bearer token or trusted identity gateway | Confirmed for MVP, 2026-09-21 |

Questions to answer:

1. Must the product accept arbitrary public YouTube tutorials, or is requiring an authorized/uploaded transcript acceptable?
2. Will users upload complete media, audio only, subtitle files, or any of these?
3. Is the product initially a personal tool, a commercial SaaS, or an instructor platform?
4. Which Python versions and package-installation policy must grading support?
5. May learner code declare third-party dependencies? If yes, how are they fetched safely and reproducibly?
6. Does the user review an assignment before it becomes active?

### Sprint 0 resolution

The product owner authorized Sprint 0 after reviewing the proposed defaults. The
working answers for the MVP are:

1. Arbitrary public YouTube downloading is not required. A public URL may import
   allowlisted metadata, but processing requires an uploaded or authorized input.
2. SRT and VTT transcript uploads are the first supported path. Authorized media
   and audio uploads are planned behind isolated workers; the API does not process
   arbitrary media inline.
3. The first release is a private personal-learning beta. The schema remains
   tenant-aware so a later SaaS transition does not require removing isolation.
4. The eventual grading image targets one pinned Python 3.12 environment first.
   Additional versions require separate versioned images and compatibility tests.
5. Third-party learner dependencies must be allowlisted and hash-pinned during a
   controlled build step. Grading sandboxes have no network access.
6. Generated assignments remain editable drafts until the user explicitly
   activates them. Activated versions are immutable after a submission.

These decisions may be revisited through an ADR, but broad implementation should
not silently contradict them.

## Decide before binary media processing

Sprint 2 starts with the already accepted SRT/VTT upload path. Binary media
processing requires the choices below before its capability is enabled; they do
not block subtitle uploads or allowlisted metadata adapters.

| Decision | Proposed default | Status |
|---|---|---|
| Transcription provider | Local-only Whisper base through an application-owned interface; no managed/paid fallback | Confirmed WAV scope, 2026-10-21; foundation only, ADR 0018 |
| Authorized binary media limits | Initial WAV path: at most 20 MB / 10 minutes; 16-bit PCM / 16 kHz / mono | Confirmed WAV scope, 2026-10-21; experimental API/form added 2026-10-23, default opt-in flag remains false (ADR 0020) |
| Local visual path | Authorized MP4 <=100 MB / 10 minutes, <=20 selected frames, local English/Turkish OCR | Delegated 2026-10-26, ADR 0021; isolated service/private checkpoints, no product upload |
| Binary input retention | Temporary originals only; delete after success, cancellation or permanent failure; retain derived transcript | Confirmed WAV scope, 2026-10-21; private lifecycle delivered 2026-10-22, inspection 2026-10-23 |

The implementation order and current assumptions are recorded in
`docs/sprint2/implementation-plan.md`. No ASR vendor or original-media retention
permission is implied by the subtitle-upload milestone.

Sprint 2 implements explicit permitted-transcript retention for retries and
complete source/project deletion (ADR 0012). The owner continued after the concrete
WAV/retention proposal on 2026-10-21; that interpretation and the narrower encoding
were surfaced in chat. ADR 0018 records the accepted local WAV scope. Only the
stateless validation/inference foundation and private checkpoint/VTT components
are delivered first; see `sprint4/asr-checkpoints-plan.md`. The subsequent private
backend slice implements dedicated jobs, original retirement and VTT handoff
(ADR 0019). Original processing eligibility expires after one hour as a surfaced
safety limit; physical deletion is separately confirmed/retried by the scheduler.
The read-only machine-generated provenance/inspection slice is now implemented
(2026-10-23): typed per-version origin, explicit accuracy caveats and original-audio
cleanup status. The subsequent bounded authenticated API/BFF/form is implemented
behind `AUDIO_UPLOAD_ENABLED=false` (ADR 0020); explicit pinned-weight/local-asr
setup and operator opt-in are required. Capability is not model health. Native
pipeline/keyword evidence and enablement status are separately recorded in
`sprint4/audio-upload-validation.md`, retaining the earlier vocabulary failure.
Re-transcription after original cleanup requires re-upload. At that milestone,
MP3/MP4, video, frame retention and broader limits remained unapproved; the narrower
2026-10-26 delegated visual decision below supersedes that for MP4/selected frames.

The same-day single-clip evaluation tool adds explicit operator-owned labels and
content-free word/character, identifier and cue-boundary diagnostics. Native input
binding checks exact WAV bytes before inference; offline fixtures are only declared
synthetic data. See `sprint4/asr-evaluation-guide.md`. It selects no quality/release
threshold, reviews no representative corpus and does not enable the upload flag.

## Decide before the provider-backed Alpha 1 release

These managed-service release gates are deferred: the owner now targets a free
local GitHub portfolio, not a production beta (ADR 0015). The selected answer
path is optional local Ollama/Qwen3 4B. Keep deterministic retrieval honest and
record actual local-model tests; this decision is not a managed-service quality
certification. Optional local semantic embeddings now use Qwen3 Embedding 0.6B
in a separately versioned 1024-D space (ADR 0016). Local ASR foundation now has the
restricted WAV scope and isolated model process in ADR 0018. ADR 0019 adds private
durable jobs and original cleanup; ADR 0020 adds the separately gated WAV upload
boundary, not default enablement or general speech-quality approval. Local frame/OCR
foundation follows in ADR 0021; visual descriptions/published frame evidence remain
unimplemented. No paid endpoint or cloud fallback is authorized.

The resumable-indexing follow-up (ADR 0017) replaces the initial 128-chunk semantic
cap with checkpointed work under the already accepted transcript input limits.
It does not authorize binary media, new providers, new retention classes or paid
calls. Target space remains immutable per job; changes require a new generation.

| Decision | Proposed default | Status |
|---|---|---|
| Answer/embedding provider and models | Optional local Ollama/Qwen3 4B answers and Qwen3 Embedding 0.6B semantic search; hash/extractive remains default | Confirmed for zero-service-spend portfolio, 2026-10-12 (ADRs 0015/0016); managed providers deferred |
| Reviewed RAG dataset and release threshold | Record local regression/smoke evidence; independent representative review before general quality claims | Production release threshold deferred; synthetic demos are not broad quality approval |

Sprint 3's local infrastructure uses the existing deterministic embedding and
extractive answer provider (ADR 0013). No model key or paid request is required.
Its streaming interface delivers validated persisted answers; remote incremental
generation, contextual follow-ups and provider-backed quality are not implied.

## Sprint 4 implementation boundary

The ordered-playlist slice continues only the accepted authorized SRT/VTT path
(ADR 0014). Playlist metadata is not audiovisual evidence. Each uploaded subtitle
has its own rights assertion and user-selected video association. The local
two-job playlist safety cap does not settle beta quotas. No binary retention,
managed ASR/vision vendor, download permission or full Alpha 2 approval is implied.

The 2026-10-23 WAV follow-up connects the already approved local audio path to those
same user-selected lesson relationships, not a new media format. The existing
1–4 `PLAYLIST_CONCURRENCY` safety cap now bounds combined ASR/index live leases,
with no retry consumed for waiting and no extension of the one-hour raw eligibility.
Alignment remains user-asserted. Metadata deletion unlinks independent audio rather
than cancelling it; complete source/project deletion remains authoritative. See
`sprint4/audio-playlist-validation.md`. The subsequent bounded visual decision is
recorded below; full video ingestion and visual quality remain undelivered.

### Delegated local visual scope (2026-10-26)

The owner delegated technical choices after the explicit MP4/OCR proposal. Select
owned/authorized MP4 <=100 MB / 10 minutes, <=20 selected frames, local English/
Turkish OCR, no paid provider/downloader and default-closed product capability.
Future originals retire on terminal paths with <=one-hour processing eligibility;
physical deletion must be confirmed separately. Permitted frames/OCR remain until
complete source/project deletion. ADR 0021 starts only a stateless isolated
FFmpeg/Tesseract foundation: H.264/avc1 yuv420p, <=1080p/60fps, zero-based input,
uniform candidates/exact-pixel deduplication, actual PTS and no audio processing.
Other codecs/formats, scene-quality claims and vision descriptions are not implied.
Durable authorization/jobs/cleanup, UI and published visual evidence remain follow-up.

The private-service continuation adds only a credential-free internal HTTP boundary
and profile-pinned worker client around that stateless parser. It receives no
application identities, publishes no host port and is not connected to current
workers. The default product capability remains closed; no durable records,
retention expansion, provider or new upload decision is implied. See
`sprint4/visual-service-plan.md` and its separate validation record.

The subsequent private checkpoint component adds migration 0013 and scoped bounded
PNG/OCR snapshots, not original retention or product enablement. It pins actor,
rights, bytes and full processing identity before inference, with one-hour
job-creation eligibility and complete source/project cascades. A saved full result
can be reused after lease recovery; interrupted inference may repeat the whole
call. Native/database roles remain separate. Video registration, dedicated queue,
original retirement/physical cleanup, object adoption and published UI/evidence
remain follow-up. See `sprint4/visual-checkpoints-plan.md`.

## Decide before Sprint 5

| Decision | Proposed default | Status |
|---|---|---|
| Assignment difficulty | User-selected, with estimated 2–4 hour default | Proposed |
| External documentation | Allowlisted official documentation only | Proposed |
| Documentation versioning | Record URL, retrieval date, detected version, and content hash | Proposed |
| Requirement labels | Covered, prerequisite, extension | Proposed |
| Assignment publication | Editable draft requiring user approval | Confirmed for MVP, 2026-09-21 |
| Deadline | Optional, learner-selected | Proposed |
| Reminder channels | In-app only | Proposed |
| Hint policy | Progressive disclosure | Proposed |

Questions to answer:

1. Should a learner be able to forbid extension topics?
2. Should an exercise target one tutorial, the entire playlist, or selected sources?
3. Can external documentation be retrieved automatically, or must users approve each domain/source?
4. What constitutes project completion?
5. Should missed deadlines affect anything beyond status and reminders?

## Decide before private beta

| Decision | Proposed default | Status |
|---|---|---|
| Language | English | Proposed |
| Project cap | 20 videos or 10 total hours | Proposed |
| Beta size | 20–50 invited users | Proposed |
| Availability | Best-effort beta; no formal SLA | Proposed |
| Production object storage | Maintained managed S3-compatible service, not the archived local MinIO CE build | Open before beta |
| Data export/deletion | Self-service request with observable completion | Proposed |
| Collaboration | Deferred | Proposed |
| GitHub integration | Deferred until file upload is stable | Proposed |
| Plagiarism detection | Deferred | Proposed |

Questions to answer:

1. What data may model providers retain, and which provider settings are required?
2. In which region must data be stored?
3. What are the acceptable processing cost and gross-margin targets?
4. Which analytics are acceptable for private learning content?
5. How long should submissions, chat, and execution logs be retained?
6. Is accessibility conformance a formal launch requirement, and at what level?

## Architecture decisions to record

Create ADRs for at least:

- content acquisition and rights modes;
- modular-monolith boundary;
- authentication/tenant model;
- background job system;
- multimodal representation strategy;
- retrieval strategy and when to introduce ANN indexes;
- model-provider interface;
- sandbox isolation choice;
- object retention/deletion;
- assignment versioning and grading determinism.
