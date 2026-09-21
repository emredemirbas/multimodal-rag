# Open decisions and proposed defaults

Resolve the blocking section during Sprint 0. Replace `Proposed` with `Confirmed` or record the selected alternative and rationale.

## Blocking before broad implementation

| Decision | Proposed default | Status |
|---|---|---|
| Initial audience | Intermediate Python developers | Proposed |
| Initial subject scope | FastAPI, Pydantic, SQL, API testing | Proposed |
| Supported source rights | Uploaded, owned, authorized, or appropriately licensed | Proposed |
| Public YouTube URL behavior | Import metadata; require a supported transcript/media path | Proposed |
| Primary submission | ZIP/file upload | Proposed |
| Grading languages | Python only | Proposed |
| Grading method | Deterministic tests plus qualitative rubric feedback | Proposed |
| Original media retention | Avoid by default; store only permitted derived artifacts | Proposed |
| Model strategy | Managed APIs behind provider-neutral interfaces | Proposed |
| Initial tenancy | Private single-user projects | Proposed |

Questions to answer:

1. Must the product accept arbitrary public YouTube tutorials, or is requiring an authorized/uploaded transcript acceptable?
2. Will users upload complete media, audio only, subtitle files, or any of these?
3. Is the product initially a personal tool, a commercial SaaS, or an instructor platform?
4. Which Python versions and package-installation policy must grading support?
5. May learner code declare third-party dependencies? If yes, how are they fetched safely and reproducibly?
6. Does the user review an assignment before it becomes active?

## Decide before Sprint 5

| Decision | Proposed default | Status |
|---|---|---|
| Assignment difficulty | User-selected, with estimated 2–4 hour default | Proposed |
| External documentation | Allowlisted official documentation only | Proposed |
| Documentation versioning | Record URL, retrieval date, detected version, and content hash | Proposed |
| Requirement labels | Covered, prerequisite, extension | Proposed |
| Assignment publication | Editable draft requiring user approval | Proposed |
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

