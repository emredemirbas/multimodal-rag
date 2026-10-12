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

## Ingestion evaluation

- transcript word/error quality on technical vocabulary;
- code identifier preservation;
- timestamp alignment error;
- scene/frame recall for meaningful visual changes;
- duplicate-frame rate;
- OCR accuracy on terminals, IDEs, and slides;
- recovery from rate limits, missing captions, deleted videos, and partial playlists;
- cost per processed hour.

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
