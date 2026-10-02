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
| Model strategy | Managed APIs behind provider-neutral interfaces | Confirmed for MVP, 2026-09-21 |
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
| Managed transcription provider | Application-owned ASR interface; provider, region and retention settings to be selected | Open |
| Authorized binary media limits | Explicit file size, duration, format and spend limits | Open |
| Binary input retention | Avoid by default; explicitly authorize any temporary original-media storage | Open |

The implementation order and current assumptions are recorded in
`docs/sprint2/implementation-plan.md`. No ASR vendor or original-media retention
permission is implied by the subtitle-upload milestone.

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
