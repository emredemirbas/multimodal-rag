# Local development

This guide covers the Docker Compose workspace, optional local processing,
recovery, tests and API access. Run commands from the repository root unless a
section explicitly changes directories. Optional model installation is a manual
operator action; normal startup and inference never download weights.

## Setup and services

Requirements: Docker with Compose, daemon access for your current user and Python
3 for the standard-library setup checker. Host-side backend development uses
Python 3.12; frontend development requires Node.js 20.19 or later.

If there is no local configuration yet:

```bash
if [ ! -e .env ]; then
  cp .env.example .env
  chmod 600 .env
fi
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Replace the example `DEVELOPMENT_AUTH_TOKEN`, PostgreSQL password and MinIO password
with separate generated values for a new setup. The token must have at least 16
characters. Keep secrets in the ignored `.env`; do not copy the example over an
existing file or rotate credentials independently of an existing database.

```bash
python3 scripts/check_local_setup.py
docker compose up --build -d
docker compose ps
```

The prerequisite checker inspects Docker/Compose availability, current-context
daemon access, configured credential-helper executables and privately resolved
base `compose.yaml` settings. It prints no raw configuration or secrets. Exit 1
means a blocker; warnings require review but exit 0. It does not run `sudo`,
repair permissions, start services, pull images/models, inspect application data
or check model health. Custom Compose overrides are not included. To check a
deliberately separate configuration, use `--env-file /absolute/path/to/local.env`;
shell environment variables retain their normal precedence.

| Service | Default address |
| --- | --- |
| Workspace | <http://localhost:3000/projects> |
| Browser demo | <http://localhost:3000/demo> |
| OpenAPI reference | <http://localhost:8000/docs> |
| API readiness | <http://localhost:8000/health/ready> |
| MinIO console | <http://localhost:9001> |
| PostgreSQL | `localhost:5433` |

Ports bind to `127.0.0.1`. The migration service runs pending SQL migrations before
the API starts. `ingestion-worker` processes transcripts; `scheduler` dispatches
the transactional outbox, recovers abandoned jobs and cleans artifacts. Optional
media/model services have separate profiles. Local MinIO is built from pinned
official source; the first build can take several minutes. Its archived CE build
is a local development dependency, not a hosted-storage recommendation.

The optional `curriculum-internal` profile provides a separate bounded curriculum
delivery worker. It is an internal development component: its workflow registry
is currently empty, unknown workflow versions fail explicitly, and there is no
public generation/run-create endpoint. Starting it does not generate assignments
or install/contact a model. It requires PostgreSQL migrations and Redis only;
the scheduler manages its independent outbox/recovery. Normal startup omits it.

Inspect or stop services without erasing data:

```bash
docker compose logs --tail=50 api
docker compose stop
```

`docker compose down` also removes the default containers/network while preserving
named volumes. Include the optional profiles you started when shutting those down.
`down -v` deletes stored application data and model volumes; do not use it as a
startup repair.

### Troubleshooting

- **Compose unavailable or `unknown flag: --build`:** run `docker compose version`
  in the same terminal and user session. A plugin installed for your user may be
  absent under `sudo`; avoid mixing configurations.
- **Docker socket permission denied:** CLI installation does not grant daemon
  access. Review [Docker's Linux access guidance](https://docs.docker.com/engine/install/linux-postinstall/)
  or rootless mode. Docker-group access grants root-level privileges; do not make
  the socket world-writable. A previously opened desktop app can retain old groups
  after a session change.
- **Missing `docker-credential-pass`:** restore the configured helper or review
  your Docker credential settings deliberately. [Helpers must be on PATH](https://docs.docker.com/reference/cli/docker/login/#credential-stores).
  The checker never executes helpers or changes credential storage. Do not post
  configuration or credentials in an issue.
- **Repeated `/health` messages:** `docker compose up --build` stays attached to
  service logs. Use `-d` to detach; healthy long-running services do not produce a
  final completion message.

## Transcript and chat workflow

The [in-app demo](http://localhost:3000/demo) uses the synthetic, repository-authored
[sample VTT](../examples/fastapi-intro.vtt), covered by the [MIT license](../LICENSE).
It creates no records automatically. Use a temporary project for the walkthrough.
The real queued uploader combines that short sample into one 00:01–00:22 chunk;
there is no associated recording or playable video.

Upload a UTF-8 SRT/VTT file of at most 2 MB with the appropriate rights statement.
Processing continues after leaving the page. The current input bounds also cap
cue and generated chunk counts; a larger file is not accepted just because its
individual cues are small.

For uncertain upload/import delivery, keep the unchanged draft and request key:
the server may already have accepted the request. Confirmed acceptance clears the
form; a changed draft creates a new key. A page reload cannot restore a browser's
selected file, so inspect sources before selecting it again. Project creation
does not use the upload replay key: refresh the list before retrying an uncertain
creation.

Retry uses retained input. Correcting malformed content requires a new upload.
Reprocessing keeps the last published generation usable until replacement succeeds.
Semantic indexing saves completed batches privately; worker recovery and explicit
retry resume committed progress, while an uncommitted batch may be recomputed.
Cancelled work retains checkpoints for retry. Only complete generations become
searchable, and old saved citations keep their original generation.

Use **Chat with tutorial evidence** for self-contained questions and optional
source filtering. Default answers quote literal evidence; the optional local model
explains retrieved evidence. Neither uses saved history as implicit conversation
context. Stopping delivery can leave a persisted answer; reload history or resend
the unchanged request to replay that logical turn.

Source filters refresh without discarding the draft. An unavailable selected
source is shown explicitly rather than silently expanding search to all sources.
Deleting a source removes saved turns that quote it, including from an open chat;
late history or delivery responses cannot restore those turns. Reprocessing does
not delete old citations. Source/project deletion removes records and separately
tracks physical object cleanup; scheduler/storage outages can delay that cleanup.
Already received or copied content cannot be recalled from a browser.

Choose **Read transcript** to browse published subtitle evidence in pages of 50
segments. Paging pins one generation, including after reprocessing. **Open latest
published transcript** switches explicitly; **Inspect evidence** opens its stable
record. Published evidence remains readable when archived or incompatible with the
current search configuration. Unfinished staging is private.

### Optional playlist metadata

`YOUTUBE_API_KEY` is optional and server-side, for official allowlisted metadata
imports only. SRT/VTT uploads need no external credential. Metadata imports never
download video/audio or establish permission to process it.

For an imported playlist, choose **Transcript belongs to** when uploading your
authorized subtitle. Optional WAV has **Audio belongs to**. These associations are
user assertions, not verified audiovisual alignment. A failed lesson can be
retried independently. Older metadata snapshots may need **Reprocess source** to
populate ordered entries; truncated snapshots are labelled.

`PLAYLIST_CONCURRENCY=1..4` limits combined live ASR/indexing leases per playlist
(default 2). Keep API, ingestion and media workers on the same value. Waiting does
not consume a failure retry but counts toward the original audio's one-hour
eligibility. Deleting metadata unlinks independent transcripts/audio rather than
deleting them; project deletion covers all sources.

## Optional local answer generation

These commands explicitly download an Ollama image and public Qwen3 4B weights:

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3:4b
ANSWER_PROVIDER=ollama docker compose --profile local-ai up -d api
```

Allow roughly 10 GB extra disk and a 16 GB RAM machine for this CPU profile; the
answer model download is about 2.5 GB. Local operation consumes CPU/RAM/electricity,
with no paid API. The model service has no published port or cloud fallback.
Questions never pull weights. Weights remain in the `ollama_data` volume.

The answer adapter allows one concurrent call with a 24-second deadline and unloads
the model after each answer to limit idle RAM and transient prompt retention.
Busy or slow hardware can produce retryable errors. With default hash retrieval,
questions need matching terms: weak evidence abstains before model invocation and
is labelled `local-evidence-policy`. Generated answers use retrieved citation IDs,
but can still be wrong; inspect the evidence.

To keep the choice across future Compose commands, deliberately edit
`ANSWER_PROVIDER=ollama` in your existing ignored `.env`. A one-command environment
override does not persist. Keep any other optional profiles already in use.

For an explicit disposable-project model probe, export your trusted local config:

```bash
set -a
source .env
set +a
python3 scripts/smoke_local_model.py
```

Return to hash/extractive operation:

```bash
ANSWER_PROVIDER=extractive EMBEDDING_PROVIDER=hash docker compose up -d api ingestion-worker scheduler
docker compose stop ollama
```

If persisted settings were changed, update them deliberately too. Switching index
spaces requires reprocessing the sources you want to search in the new mode.

### Optional semantic search

Explicitly install the separate embedding model, then configure API and worker
consistently:

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3-embedding:0.6b
EMBEDDING_PROVIDER=ollama ANSWER_PROVIDER=ollama docker compose --profile local-ai up --build -d api ingestion-worker scheduler frontend
```

The embedding download is about 639 MB. The application pins an approved manifest
and a 1024-dimensional index space; incompatible manifests fail safely. Existing
sources need **Reprocess source**. The UI excludes incompatible indexes, while
old evidence stays inspectable and failed replacement preserves the prior index.
`ANSWER_PROVIDER=extractive` can also use semantic retrieval without answer-model
inference. Persist choices only in the existing `.env`.

Search combines exact project-filtered vectors, full-text candidates and an
identifier boost. The raw-cosine guard is a heuristic, not confidence or
faithfulness: valid paraphrases can be rejected. Query embeddings have a six-second
inference bound and share a 28-second budget with answer generation.

Indexing uses eight chunks per batch and at most eight batches per delivery,
starting no new inference after 48 seconds. Unfinished work requeues without a
failure retry. Target space and chunk manifest stay pinned; restore the original
configuration to retry a pinned job or start a new generation with **Reprocess
source**. Usage records model/index identities and nullable reported tokens with
zero billed API cost.

```bash
set -a
source .env
set +a
python3 scripts/smoke_semantic_search.py
python3 scripts/smoke_semantic_search.py --long
```

The optional long probe exercises multi-delivery indexing with 129 chunks. These
probes create and clean their own projects; they require explicitly installed
weights and running services.

## Optional WAV transcription

Disabled by default (`AUDIO_UPLOAD_ENABLED=false`). Supported input is authorized
WAV, signed 16-bit PCM, 16 kHz, mono, at most 20,000,000 bytes and 10 minutes.
MP3 and other encodings are not accepted by this path. Inference runs in bounded
children in an isolated, credential-free private service, with no paid fallback.

Explicit setup downloads about 148 MB of Whisper-base files from a pinned revision
and verifies each SHA-256:

```bash
docker compose build asr
docker compose --profile asr-setup run --rm --no-deps asr-model-install
docker compose --profile local-asr up -d --wait --wait-timeout 120 asr
```

Verify an owned/authorized supported WAV of at most 30 seconds without writing
application data or printing recognized text:

```bash
docker compose --profile local-asr run --rm -T --no-deps --entrypoint python asr \
  -m app.asr.smoke --language en < /absolute/path/to/owned-probe.wav
```

Use `--language tr` or `auto` as appropriate. The service has no host port, app
credentials or user-data mount, denies new sockets after binding, and requires
Linux seccomp support. Missing isolation/weights fail closed. It is not a sandbox
for learner code.

After explicit setup, enable the UI/API and worker:

```bash
AUDIO_UPLOAD_ENABLED=true docker compose --profile local-asr up --build -d --wait --wait-timeout 120 api frontend media-worker ingestion-worker scheduler
```

Keep other active profiles too. To persist opt-in, edit the existing `.env` and
include `local-asr` when starting the stack. Configuration availability is not
model readiness or speech accuracy. To reject/hide new WAV uploads again:

```bash
AUDIO_UPLOAD_ENABLED=false docker compose up -d api
```

Use **Experimental local WAV transcription**, selecting rights, language and the
temporary-retention acknowledgement. Uncertain delivery uses the unchanged request
key; stopping upload delivery is not job cancellation. Follow transcription,
indexing and cleanup independently. Optional playlist association is user-asserted.

Original processing eligibility lasts one hour including queue waiting. Success,
cancellation, permanent failure or expiry retires the original for deletion.
Only **Original audio deletion confirmed** establishes physical cleanup; failed
cleanup can be retried separately. Derived VTT remains until source/project deletion.
Reindexing uses that text and preserves the original ASR provenance. Transcribing
again requires a new authorized upload, with no original player/download provided.

ASR text and timestamps are unreviewed and may misrecognize technical identifiers.
Upload corrected SRT/VTT separately rather than rewriting saved citations.
[ASR diagnostics](sprint4/asr-evaluation-guide.md) compare explicit operator-owned
labels without publishing transcript content; synthetic/native probes do not
establish representative speech quality.

## Optional MP4, frames and OCR

Disabled by default (`VIDEO_UPLOAD_ENABLED=false`), independently of WAV. The
accepted standalone upload is authorized MP4, at most 100,000,000 bytes and 10
minutes, H.264/avc1 yuv420p, at most 1080p/60 fps, zero-based and unrotated. AAC,
if present, is ignored. This path does not transcribe sound or supply original
video playback or playlist association.

Build/start the private visual service and worker explicitly:

```bash
VIDEO_UPLOAD_ENABLED=true docker compose --profile local-visual up --build -d \
  api frontend scheduler ingestion-worker visual-worker
```

This command's flag override is temporary; persist only through deliberate changes
to the existing `.env` and profile selection. Building the isolated parser installs
FFmpeg/Tesseract and small Debian English/Turkish OCR assets, without Ollama/Whisper
weights or paid requests. Starting the parser alone does not enable uploads.

The form requires rights, OCR language and permission to retain selected frames
and OCR until source/project deletion. Prefer explicit English or Turkish:
combined `en+tr` has known exact-term recognition failures. Ordinary sampling is
uniform with at most 20 selected frames and exact-image deduplication. OCR can
misread code, symbols and text; sampling can miss important changes.

The durable workflow performs extraction, complete-gallery publication and OCR
indexing as separate recoverable jobs. Partial galleries/checkpoints stay private;
search activates only a complete index. **View selected frames** shows actual PTS,
unreviewed OCR and processing origin. Frame citations retain stable IDs and exact
point timestamps. Public video reprocess is unavailable; after original cleanup,
new extraction needs a fresh authorized upload.

API/BFF enforce byte/time/part-count bounds and one video delivery per process.
Raw-video eligibility expires after one hour. Retirement is distinct from physical
deletion: follow pending/failed/confirmed cleanup, including after indexing.
Derived retries reuse retained work; source/project deletion covers all artifacts.

### Standalone diagnostic

For a no-network operator probe without application records:

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps visual-inspect \
  --authorized-input --language en < /absolute/path/to/owned-tutorial.mp4
```

The output is counts, hashes and processing identity, not PNG/OCR content. Your
host file is untouched. `visual-tools` is for one-shot commands; do not add it to
ordinary startup. An authored private HTTP boundary check is also available:

```bash
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.http_selftest
```

The [visual guide](sprint4/local-visual-guide.md) records native limits and
[OCR diagnostics](sprint4/visual-evaluation-guide.md) compare labels bound to exact
input bytes. Coverage is not scene recall or an automatic quality threshold.

### Change-aware selection and temporal inspection

[Change-aware OCR](sprint4/change-ocr-guide.md) is an explicit experimental
`VISUAL_SELECTION=change` worker opt-in, not the default. It can find transient
views but miss small edits or spend its budget on cursor movement. A job keeps its
pinned selection identity; changing defaults does not convert existing evidence.
[Paired diagnostics](sprint4/code-policy-evaluation-guide.md) expose gains and
losses separately.

In a retained gallery, **Align with a transcript** compares published frame/OCR
and transcript generations. Choose the same recording, confirm that assertion,
and set a millisecond offset (positive looks later in the transcript). Missing
spans remain gaps. This is read-only temporal inspection, not verified semantic
agreement, combined citation or a persisted source relationship. See
[timeline behavior](sprint4/timeline-alignment.md).

### Optional image descriptions

Descriptions require their own default-off `FRAME_DESCRIPTIONS_ENABLED` flag,
`local-ai`/`local-vision` profiles and an explicitly installed `qwen3.5:4b` in the
Compose Ollama model store. Pin its full 64-character local manifest digest in
`VISION_MODEL_DIGEST`; a host Ollama installation is a different store.

Follow the [description setup guide](sprint4/frame-descriptions.md#setup--explicit-operator-action-not-part-of-a-default-start)
for read-only local inventory and exact configuration. No API/job installs weights.
The dedicated worker processes retained images without reopening original video.
Complete descriptions publish and index separately labelled unreviewed model
interpretations; old OCR citations remain stable. Model output can be incorrect
and does not verify code or audiovisual alignment.

## Authentication and API

The local Compose stack uses one development principal. The Next.js server
forwards `DEVELOPMENT_AUTH_TOKEN` to the API server-side; do not put it in a
`NEXT_PUBLIC_*` value or send browser-controlled tenant selectors. `X-Tenant-ID`
is not trusted. Direct requests require bearer authentication:

```bash
set -a
source .env
set +a
curl -H "Authorization: Bearer $DEVELOPMENT_AUTH_TOKEN" \
  http://localhost:8000/api/v1/projects
```

Source only a trusted local configuration. A trusted identity-gateway adapter is
available; its networking requirements are in [ADR 0011](adrs/0011-sprint1-identity-adapters.md).
All project-owned operations enforce tenant and project scope. Unknown, deleted
or differently scoped projects return the same safe `404` shape.

Use [OpenAPI](http://localhost:8000/docs) for current request/response schemas.
The main endpoint groups are:

| Group | Routes |
| --- | --- |
| Projects | `GET/POST /api/v1/projects`, `GET/PATCH/DELETE /api/v1/projects/{project_id}`, `POST .../archive`, `POST .../restore` |
| Sources | `GET/POST .../sources`, `POST .../sources/uploads`, `GET/DELETE .../sources/{source_id}` |
| Recovery | `GET .../jobs/{job_id}`, `POST .../sources/{source_id}/retry`, `/cancel`, `/reprocess` |
| Cleanup | `GET .../cleanup/{cleanup_id}`, `POST .../cleanup/{cleanup_id}/retry` |
| Chat | `GET/POST .../conversations`, `GET .../conversations/{conversation_id}`, `POST .../conversations/{conversation_id}/messages` (SSE) |
| Evidence | `GET .../evidence/{segment_id}`, `GET .../sources/{source_id}/transcript` |
| Stateless answer | `POST .../questions` |
| Experimental media | `POST .../sources/audio`, `POST .../sources/video`, `GET .../sources/{source_id}/frames`, `GET .../frames/{frame_id}/image` |
| Experimental descriptions | `GET/POST .../sources/{source_id}/descriptions` |
| Temporal inspection | `GET .../sources/{source_id}/alignment` |

`...` means `/api/v1/projects/{project_id}`. Transcript pages use an optional
`generation` parameter, fixed 50 segments per page, and require a generation after
page 1. Authenticated `GET /api/v1/ingestion/capabilities` and `/video-capabilities`
report configured media availability and fixed limits, not service health.

Operational routes: `/health/live`, `/health/ready`, `/health` (compatibility),
`/metrics` and authenticated `/api/v1/runtime` for nonsecret mode/index settings.
The deprecated `POST .../sources/transcripts` compatibility endpoint is limited
to development/test hash mode; ordinary ingestion uses queued uploads.

### Prepare learning material

Open **Prepare learning material** in a project. Select 1–20 sources with published
text and explicitly choose experience, difficulty, language and available effort.
Source versions stay fixed in the saved selection even if processing runs again.
Prerequisites, extensions and official documentation are unchecked by default;
these preferences do not start generation or retrieve any page.

Save the selection and bookmark its page to return later. There is no context
list yet; an unsaved form is not recovered after a reload. If delivery is uncertain,
**Check context delivery** repeats the original selection unchanged, even if the
source inventory refreshed. Editing the form starts a different selection.

For a selection that permits official documentation, choose the English FastAPI
First Steps catalog page, review its MIT attribution/unknown-version policy and
check the explicit retrieval/retention consent. **Save document approval** stores
permission only. **Capture document** separately retrieves the page. Opening the
page, changing preferences, checking status or refreshing approvals never captures.

Retained text is literal text, with server retrieval time, canonical URL, explicitly
unknown version, stable excerpt links, hashes and full MIT notice. Use **Check
capture delivery** for an uncertain attempt; **Retry capture** explicitly starts
a new attempt after a fixed failure. The original approving member must capture.
Archived projects permit reading/deleting saved copies but require restoration
for new approval/capture. Deletion confirmation hides retained text immediately;
if delivery is uncertain, check the deletion result before showing a copy again.
Deleting a selected source also removes its saved context and documents. Deleting
a document also deletes any draft that selected it in any revision, including the
entire revision history and replay receipts; the confirmation explains this effect.

Follow **Review saved assignment drafts** from a saved selection to see its current
drafts. Open one to inspect labelled requirements, original evidence, criteria and
progressive hints; edit wording and effort to save a new revision. Structural links
and selected documents stay fixed in this editor. History is read only. A conflict
requires explicit discard/reload, while an uncertain save repeats its unchanged
body/key. Refresh/focus rechecks dependencies; unconfirmed deletion hides text until
checked. Bookmark the draft URL to recover the authoritative saved version.

Assignment generation and activation remain unavailable. Lists can be empty: this
UI does not manufacture sample/generated drafts. Existing drafts authored through
the draft API are reviewable; no public creation/generation control is added.
No project text is stored in browser local/session storage; recovery uses the saved
page's URL and authoritative server state.

### Official documentation API

The backend supports a saved context's explicit per-document consent and separate
capture operation. The learner screen uses this same boundary; the separate draft
API can bind selected captured IDs after migration 0026.
Use the authenticated OpenAPI reference for the precise request schemas, and
the [data/API contract](05-data-model-and-api.md#curriculum) for routes and replay
behavior. Requires PostgreSQL migration 0025; in-memory mode returns 503.

1. Save a context with selected published source generations and explicit
   `allow_external_documentation: true`. Normal contexts remain tutorial-only.
2. Read `/api/v1/projects/{project_id}/curriculum/documentation/catalog` and choose
   the fixed `fastapi-first-steps-en` entry after reviewing its URL, license,
   unknown-version policy and fingerprint.
3. Approve it under `/curriculum/contexts/{context_id}/documentation`, supplying
   a fresh `idempotency_key`, its `catalog_id`, `catalog_sha256` fingerprint and
   explicit `consent: "retrieve_and_retain"`. This saves permission without fetching.
4. Only when retrieval/storage is intended, POST a separate `{idempotency_key}`
   to `/curriculum/documentation/{document_id}/capture`. Only the original approver
   can capture. This is the operation that contacts the official page.
5. Read/list the saved inert text, stable excerpts, hashes, server retrieval date
   and MIT attribution. Deleting the approval deletes its copy and command receipts;
   source/context/project deletion cascades them too.

Preserve an unchanged request key when delivery is uncertain. A successful receipt
returns the same immutable snapshot; it never refreshes the page. A failed key
replays its fixed error; an intentional retry needs a new key. Concurrent captures
return 409. A policy change requires current catalog approval. Restoring an
archived project is necessary for new captures; saved reads/replays/delete work.

Only one exact HTTPS page is supported, with no redirects, proxy use, arbitrary
URLs or crawling. DNS/private-address checks, verified pinned TLS, child-process
time/resource limits and strict byte/parser bounds fail closed; some site changes
may require a reviewed catalog/parser update. Linux is required for child resource
limits. Text remains untrusted and is never rendered as HTML or executed. This
does not enable external-topic generation or certify the local model's quality.
Automated validation uses authored local fixtures and no live documentation fetch.

### Draft document binding API

Existing draft create/replace endpoints accept optional `documentation_ids`
(default `[]`, up to 20 unique IDs). Use captured documents belonging to the same
saved context, with the context's explicit documentation/prerequisite/extension
permissions as appropriate. Requirements cite their stable excerpt IDs; metadata,
text, timestamps or URLs supplied by a client cannot create authoritative evidence.
Binding performs no retrieval or model call. Only cited projections are returned;
the saved selection is included as `documentation_ids` for replacement/recovery.

The selection replaces the previous revision's selection in full. Its canonical
order makes a reordered retry identical; changing the selection changes the request
identity. Old omitted/empty selections keep their existing replay behavior. Reading
an old revision uses its original captured text and retained approval policy,
while its catalog ID/URL must still be allowed by the application.
Any historically selected document is a dependency, even if uncited or later
dropped. Deleting it removes the complete logical draft/history/receipts and result
pointer; unrelated drafts remain. Create a separate draft without that document
when independent retention is needed.

This API is a structural binding boundary. It does not certify semantic evidence,
enable model generation, activate an assignment or introduce submission/grading.

## Testing

Use separate disposable resources. Integration and smoke tests create and remove
their own projects/schema/artifacts; do not point cleanup commands at real data.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=. pytest -m "not integration"
```

For full integration, run PostgreSQL/pgvector, Redis and MinIO in a disposable
Compose stack, then export its configuration. The real-worker probes create
isolated DB schemas, Redis key prefixes and their own Celery processes; they do
not kill the ordinary worker or flush shared Redis.

```bash
cd backend
set -a
source ../.env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=. pytest -m integration --tb=short
```

Use the environment file of the intended test stack. Ordinary CI does not download
model weights; local HTTP fixtures and actual database/worker checks exercise
recovery independently of native model quality.

Curriculum delivery tests need only disposable PostgreSQL/pgvector and Redis.
Set `TEST_DATABASE_URL`, `TEST_CURRICULUM_REDIS_URL` and
`TEST_CURRICULUM_WORKER=1`, then run `PYTHONPATH=. pytest -m integration` from
`backend/`. Install pgvector in the disposable database's public schema before
parallel isolated-schema suites. These tests start and kill only their own worker
processes, delete only random Redis prefixes and drop only their synthetic DB
schemas; they require no MinIO/model service. The backend integration CI job
includes them. Real processors are never replaced by fixtures in the product.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

### Running-application smoke checks

With the intended disposable stack running in default hash/extractive mode:

```bash
set -a
source .env
set +a
python3 scripts/smoke_sprint1.py
python3 scripts/smoke_sprint2.py
python3 scripts/smoke_sprint3.py
python3 scripts/smoke_transcript_viewer.py
```

These exercise lifecycle, queued ingestion, reprocessing, failure/retry, stable
citations and cleanup of their own projects. The transcript-viewer smoke also
supports optional semantic mode and makes no answer-model calls.

An explicitly enabled native visual workflow probe uses authored MP4 on stdin,
with visual/ingestion workers, scheduler, API, frontend and backend dependencies:

```bash
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.http_selftest --fixture | \
  VIDEO_WORKFLOW_SMOKE=1 PYTHONPATH=backend python3 scripts/smoke_video_workflow.py
```

Export matching development credentials/ports first; this script does not read
`.env` or run migrations. On a disposable opted-in stack, the additional
`VIDEO_UPLOAD_SMOKE=1` and `VIDEO_UPLOAD_LARGE_SMOKE=1` flags exercise the public
upload/BFF/SSR path and 100 MB input. `FRAME_DESCRIPTION_SMOKE=1` additionally
requires explicit local vision model setup; it never pulls weights. These are
synthetic wiring probes, not representative media-quality review.

### Retrieval regression

```bash
PYTHONPATH=backend python3 scripts/evaluate_rag.py
PYTHONPATH=backend python3 scripts/evaluate_rag.py --postgres
```

The PostgreSQL variant needs exported local credentials. This synthetic set is a
regression check, not an independent model-quality benchmark.

A deterministic in-memory proof is available without Docker/model credentials:

```bash
cd backend
PYTHONPATH=. python3 -m app.demo
```
