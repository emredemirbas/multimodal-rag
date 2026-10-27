# Testing and evaluation strategy

The product needs ordinary software tests, security tests, model-system evaluations, and learning-outcome measurements. None substitutes for the others.

## Software test pyramid

### Unit tests

- Pydantic validation and domain state transitions
- timestamp and transcript normalization
- chunking boundaries
- rank fusion and citation formatting
- assignment-schema validation
- quota calculations
- deadline/timezone behavior

### Integration tests

- API plus PostgreSQL authorization
- Celery idempotency and retry behavior
- object upload/download and deletion
- full-text and vector retrieval
- provider adapters using recorded/synthetic fixtures
- source reprocessing and version transitions
- sandbox coordinator protocol

### End-to-end tests

- create project → add supported source → process → chat with citation;
- import playlist with partial failure → retry → ready;
- generate/edit/activate assignment;
- submit → grade → feedback → resubmit;
- delete project → verify all stores;
- expired/unauthorized object and project access.

## RAG evaluation

Build a labeled dataset from a small number of representative tutorials. Include:

- conceptual questions;
- exact API/function names;
- error messages and commands;
- cross-video synthesis;
- visual-only questions;
- questions unsupported by the material;
- adversarial questions attempting cross-project access or prompt injection.

Track:

- retrieval recall@k;
- reranker quality;
- citation precision and timestamp accuracy;
- groundedness/faithfulness;
- appropriate abstention;
- cross-project leakage rate, which must be zero in tests;
- latency and cost by query class;
- performance by modality.

Do not rely solely on LLM-as-judge. Use human labels for the core benchmark and deterministic checks for citation ownership/timestamp relationships.

Optional semantic mode has an explicit real-model/real-worker smoke with English
and Turkish paraphrases, unsupported questions, stable timestamps, reprocessing
and owned-project cleanup. Report it separately from the 19-question deterministic
regression and synthetic HTTP/isolation tests. A small successful smoke and its
experimental cosine floor do not establish representative recall or faithfulness.
CI does not start/download local weights. See `sprint3/semantic-search-validation.md`.

Checkpoint recovery also has an isolated actual Celery SIGKILL probe after the
first saved batch, followed by replacement-worker continuation and duplicate
delivery. Fixture calls are counted by chunk to distinguish resumability from
simply redoing all inference. Check private staging visibility, scope/lease/model/
parser fences, failed/cancelled replacement, atomic promotion and deletion.
Native `scripts/smoke_semantic_search.py --long` is explicit and never pulls weights.

Published transcript browsing has separate ordering/pagination, tied-timestamp,
legacy >10,000 segment, read-snapshot deletion race, archive, membership/tenant/
project/source and unpublished-generation tests. Verify old pages/evidence remain
stable across reprocessing/index-space changes; staging and frames stay excluded.
The production SSR smoke checks 53 segments, pinned page links, literal hostile
text, version recovery and owned-data cleanup, with no answer generation.

## Ingestion evaluation

- transcript word/error quality on technical vocabulary;
- code identifier preservation;
- timestamp alignment error;
- scene/frame recall for meaningful visual changes;
- duplicate-frame rate;
- OCR accuracy on terminals, IDEs, and slides;
- recovery from rate limits, missing captions, deleted videos, and partial playlists;
- cost per processed hour.

### Local ASR foundation

The local WAV ASR foundation adds strict RIFF/PCM limits, fake local HTTP identity/
timeline/output/capacity/error tests, atomic/hash-checked setup tests and an actual
inherited kernel seccomp probe. CI builds the optional image and checks isolation
without Whisper weights. Native speech recognition is explicit and separately
reported; it is not a broad quality benchmark. Audio registration, original
retention/terminal cleanup and media queue authorization remain required follow-up
coverage before enabling product uploads (ADR 0018).

The private checkpoint component separately tests actual PostgreSQL staging,
concurrent saves, lease-loss/retry, scope/membership/cancellation/deletion fences,
input/profile/language drift, output integrity and deterministic timestamp-preserving
VTT assembly. Staging never becomes retrieval/citation evidence. Verify all-silent
input fails honestly and that the existing API still rejects WAV. Its lease-expiry
test is not a real ASR-worker SIGKILL or end-to-end media-ingestion claim; those
require the later queue, original-retention/cleanup and atomic-adoption slice.

The private media-backend slice now adds those queue/lifecycle components and a
separate actual SIGKILL probe: after one saved ASR window, kill only the test-owned
media worker, recover its lease, and resume through dedicated media and ingestion
queues. Count fixture inference per window, verify stable provenance, ordinary
index activation, raw MinIO deletion and complete project cleanup. Inference is a
controlled fixture, not native speech-quality evidence. Also cover post-PUT
revocation, unique-candidate orphan cleanup, TTL, cleanup failure/exhaustion/retry
and cross-scope cleanup FK rejection. All vector/ingestion tests use isolated
schemas; never run application migrations as an incidental test setup step.

Machine-generated inspection has separate provenance and lifecycle checks:
source artifact versus published-generation origin, metadata drift, old
citations/history across reindexing, ordinary/legacy absence, revoked/foreign/
deleted reads, expiry versus physical deletion and actor-owned cleanup retry.
Frontend contracts reject mixed page/segment origins and impossible cleanup
states. UI tests verify automatic/unreviewed labels, literal untrusted text,
corrected-subtitle guidance, cleanup-only visibility-aware polling and failure
recovery. Full local regression additionally uses newly created disposable service
containers with allowlisted test credentials/DSNs and no application volume mounts;
schema/queue/object prefixes remain defense in depth. No native-quality claim is
implied by fixture inference or these read-only views.

The separate opt-in upload boundary tests authentication/disabled rejection before
body reads, actual chunked-byte bounds despite false Content-Length, slow reads,
strict rights/language/retention/field counts, actual WAV encoding/duration/size,
archived/foreign scope, idempotency and durable queue handoff. Browser tests cover
Origin/Host before forwarding, fail-closed capability, scoped minimal receipts,
unchanged subtitle/chat limits and safe public errors. Form tests distinguish
delivery abort from job cancellation, retain the draft/key on uncertainty, verify
acceptance before reset, and hide uploads on archived/unavailable projects.

Native verification runs in a new disposable Compose project with test credentials,
fresh data volumes/networks/queues, loopback random ports and only the preinstalled
public weights shared read-only. Verify >2 MB BFF upload, actual private ASR and
Celery handoff, production SSR/versioned provenance, raw physical deletion,
retained-VTT reindex/replay, then complete owned source/project/object cleanup.
Define synthetic keyword expectations before inference and report mismatches
separately. No human/technical/multilingual/timestamp quality approval is implied.
Do not use application volumes or actual `.env` for these broad/native probes.

WAV-to-playlist tests additionally cover concurrent binding/replay, byte-compatible
standalone hashes, busy ASR/index replacement, scoped/stale item rejection,
post-PUT revocation/orphan cleanup, snapshot/video identity changes, metadata
unlinking and complete source/project cleanup. Concurrent mixed-queue claims share
one cap; committed ASR continuations and downstream indexing must obey it without
extra failure attempts. Verify configured limits reach media workers as well as
ordinary workers. UI/BFF checks preserve the selected lesson/key across busy and
stale polling, reject mismatched association receipts and retain standalone use.
Native production-BFF smoke uses fixture metadata (not a live YouTube import),
authored synthetic speech and a shared cap of one; count native inference events
to distinguish same-key replay/reindex from retranscription.

### Local ASR quality diagnostics

The local single-clip ASR evaluator now separates normalized WER/CER, literal
identifier recall, silence hallucination and unique-phrase enclosing-cue timing
coverage/error. It binds native references to exact WAV bytes before inference;
offline input binding is only declared. Arithmetic, Unicode/Turkish, exhaustive
small distance-oracle, missing/ambiguous timing, invalid JSON/work limits and safe
CLI/native-probe tests are synthetic software evidence, not a reviewed corpus.
See `sprint4/asr-evaluation-guide.md`. No quality threshold, automatic enablement,
representative speaker/technical benchmark or word-level alignment is implied.

### Local visual foundation

Test top-level MP4/metadata bounds before native decoding, fixed codecs/timelines,
bounded sampling, actual PTS, strict P5 pixels, deterministic PNG/CRC, exact-pixel
deduplication without erasing single-pixel code changes, literal OCR, content-free
reports, model/profile drift and child deadline/environment/resource limits.
Optional CI builds the minimal OCR image and generates authored English/Turkish
cards in a new no-network/read-only/resource-bounded container. Report known-language
OCR checks separately from mixed-language failures; synthetic cards are not a
representative scene/code/terminal benchmark. No application records or media are
used. Durable authorization/recovery/storage/deletion tests remain required before
product video enablement. See `sprint4/local-visual-validation.md`.

The separate private HTTP boundary tests real loopback framing, connection/work
capacity, absolute trickle deadlines, release/recovery, safe errors/logs, profile
pinning and input/result binding. Validate base64/PNG chunks, CRC, geometry,
bounded decompression, timestamps/sampling and exact decoded-pixel duplicates,
including malformed remote output. Verify no proxy, redirect or provider retry.
An additional disposable no-network native probe starts the actual filtered server
child, transports authored PNG/Turkish OCR over its private listener and rejects a
changed pinned identity before repeat inference. This remains synthetic component
evidence, not durable video recovery/deletion or representative OCR quality.

Private visual checkpoints add real PostgreSQL tests for concurrent begin/save,
duplicate no-overwrite, lease recovery, stale/foreign scope/source/generation/
initiating actor, membership revocation/locking, cancellation, wall-clock expiry,
fixed deadline across retries, incomplete/corrupt manifests and atomic rollback.
Check the 20-frame/Unicode character-byte limits, scoped FKs and source/project
cascades; migrate existing published data without modifying prior checksums.
Private staging must never appear in retrieval/citations/usage or contentful logs/
metrics. These fixtures make no native request or object PUT: a real video worker
SIGKILL, original cleanup and atomic object adoption remain later workflow gates.

The subsequent private video workflow adds real PostgreSQL registration/race,
scope/auth/rights, orphan cleanup, expiry/terminal retirement, original integrity,
cached-result recovery and once-only preparation/usage tests. A test-owned Celery
process is SIGKILLed after a committed complete snapshot, then replaced through
real Redis and MinIO: provider construction and original GET are forbidden on
recovery, native inference is explicitly a synthetic fixture in this test.
Cleanup must verify actual object absence; source/project deletion removes every
private row/byte. Native HTTP/OCR tests remain separate component evidence, not a
claim that the fixture is representative native video quality. Public video upload,
final derived-object adoption and visual retrieval/quality remain later gates.
See `sprint4/video-worker-validation.md`.

Retained-gallery tests add one-PNG continuations, no partial visibility, immutable
origin, maximum 20 frames including blank OCR, derived cancel/retry after raw
deletion, scope/token/actor/wall-clock fences and manifest/object corruption.
Exercise a real worker SIGKILL after actual MinIO PUT but before DB adoption:
the orphan reservation survives, cleanup removes only that candidate, and replacement
deliveries retain the complete gallery without provider calls. Test protected image
reads, reauthorization after object access, source/project cascades and PNG cleanup.
Frontend contracts/proxy/render tests cover no-store/byte/time bounds, source mismatch,
unsafe OCR, loading/empty/error/retry and no false searchable-state claims. Keep
fixture process-loss evidence distinct from the separately exercised actual native
pipeline; neither establishes representative OCR/scene quality. See
`sprint4/visual-gallery-validation.md`.

Retained-OCR indexing additionally tests literal Unicode chunk offsets/stable IDs,
zero-PTS point evidence, hash/semantic vector-space separation, complete-only
promotion, saved batch corruption and actual post-write wall-clock rollback.
Cover internal command scope/concurrency/replay, cancel/retry, empty OCR, provider
drift, immutable extraction/frame origin in new/old evidence/chat, scoped FKs and
full deletion. An actual owned Celery worker is killed after eight saved vectors;
replacement must not recompute them or read/write original objects. Keep that
controlled-inference recovery evidence separate from the authored native OCR ->
gallery -> actual ingestion index -> production BFF/SSE/history/frame-link probe.
Neither establishes representative OCR/scene quality or native semantic recall.
Frontend contracts must accept frame points but reject transcript points/mixed
origins, and preserve literal OCR, exact protected frame links and honest index
state. See `sprint4/visual-index-validation.md`.

## Assignment evaluation

Maintain a reviewed set of generated assignments and score:

- objective alignment;
- completeness and internal consistency;
- feasibility within estimated time;
- acceptance-criteria testability;
- correctness of `covered`/`prerequisite`/`extension` labels;
- citation correctness;
- difficulty calibration;
- version compatibility;
- whether hints reveal the solution prematurely.

## Grading evaluation

- deterministic reproducibility across repeated runs;
- false pass and false fail rates;
- agreement with expert human rubric scores;
- resistance to test tampering;
- dependency and environment reproducibility;
- sandbox isolation and resource-limit enforcement;
- feedback actionability and consistency;
- correct separation of test facts from model suggestions.

## Security testing

- horizontal and vertical authorization tests;
- direct-object-reference attempts;
- vector/retrieval cross-tenant tests;
- SSRF and redirect bypass attempts;
- prompt-injection corpus;
- archive bombs and malformed parser inputs;
- sandbox network, filesystem, process, syscall, and resource escapes;
- signed-URL expiry and object-key manipulation;
- secret scanning of images, logs, and artifacts;
- deletion completeness.

## Learning-outcome evaluation

For beta users, measure with consent:

- pre-task versus post-task knowledge checks;
- success on a novel transfer task;
- attempts and hints before success;
- time to independent completion;
- assignment completion and resubmission rate;
- learner confidence versus measured performance;
- qualitative usefulness of citations and feedback.

## Release gates

Before Alpha 1:

- project-isolation tests pass;
- baseline retrieval/citation benchmark is recorded;
- unsupported questions abstain reasonably.

Before Alpha 3:

- sandbox threat review passes;
- test execution is deterministic;
- assignment quality benchmark is reviewed by a knowledgeable developer.

Before private beta:

- deletion and backup restoration are exercised;
- no open critical security findings;
- cost and rate limits are active;
- observability covers ingestion, retrieval, generation, and grading;
- known model-quality limitations are documented.
