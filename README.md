# Multimodal Tutorial Learning Workspace

A local, zero-service-spend GitHub portfolio project: authorized programming
tutorials become searchable, citation-backed learning material. The selected
first release is **RAG portfolio v1**: the default local transcript-to-answer
workflow, inspectable evidence and complete deletion. Assignments, submissions,
hardened grading and the learning/feedback loop remain on the roadmap after v1;
this is not a production/SaaS deployment.

Current stage: **Sprint 4**, with a constrained local multimodal workflow, not a
finished learning/assessment platform. Portfolio v1 acceptance is tracked in the
[finite scope, completion criteria and delivery status](docs/09-delivery-status.md).
Optional local models and media features remain experimental opt-ins. Independent
owned/licensed real-video review remains open outside v1 and still blocks full
Sprint 4/Alpha 2 approval.

Sprint 0 validated the transcript-to-cited-answer path. Sprint 1 adds the product
foundation around it:

- an accessible Next.js project workspace;
- authenticated, tenant-scoped project management;
- create, list, view, rename, archive, restore, and delete flows;
- additive PostgreSQL migrations and base processing-job tables;
- separate migration, API, frontend, PostgreSQL/pgvector, Redis, and MinIO
  Compose services;
- backend, PostgreSQL integration, frontend, and image-build CI jobs.

Sprint 2 adds bounded SRT/VTT uploads, retained artifacts, Celery ingestion,
transactional outbox delivery, timestamped/versioned chunks, processing progress,
retry/cancel/reprocess controls and tracked source/project file cleanup. Optional
official YouTube video/playlist metadata never downloads audiovisual content.
Sprint 3 adds a labelled offline extractive chat baseline with persisted SSE
delivery, source filters, hybrid rank fusion/reranking and inspectable stable
timestamp citations. Optional Ollama/Qwen3 4B now provides real local answers;
the default remains a keyless extractive demo. Optional Qwen3 Embedding 0.6B adds
real local multilingual semantic retrieval; default retrieval stays 64-D hash/
lexical. Old indexes are never mixed with the 1024-D model space. Binary media/ASR
is off by default; the restricted local WAV path below is an experimental opt-in.
The initial Sprint 4 slice adds ordered playlist metadata snapshots, explicit
video-to-subtitle associations and bounded independent transcript processing.
Subsequent slices add isolated MP4 frame/OCR processing, retained galleries,
frame-backed citations and standalone uploads behind `VIDEO_UPLOAD_ENABLED=false`.
Experimental change-aware selection is an explicit local worker opt-in; uniform
sampling remains default. The retained gallery also offers a version-pinned
frame/transcript timeline with explicit user-asserted source pairing. Optional
local Qwen3.5 vision descriptions now interpret retained images, stay separately
labelled from OCR and feed versioned frame evidence/citations. They require an
explicit full model digest and `FRAME_DESCRIPTIONS_ENABLED=true`; the flag defaults
to false. Nothing downloads automatically. See [setup, validation and known model errors](docs/sprint4/frame-descriptions.md).
Independent real-example audiovisual/quality verification remains the final
Sprint 4 closure gate; software/native probes do not establish quality approval.

Optional isolated Whisper-base now connects authorized restricted WAV upload to
a dedicated media queue, resumable transcription, retained VTT/indexing, versioned
unreviewed provenance and tracked original-audio cleanup. **`AUDIO_UPLOAD_ENABLED`
defaults to false**; explicit model/worker setup and operator opt-in are required.
This is not video/OCR/vision or full multimodal completion (ADRs 0018–0020).

Published transcripts can also be browsed directly in chronological, version-
pinned pages, without asking a question or invoking a model. Private unfinished
indexing batches are never exposed as evidence.

## Read first

1. [`docs/01-product-brief.md`](docs/01-product-brief.md)
2. [`docs/02-requirements.md`](docs/02-requirements.md)
3. [`docs/03-system-design.md`](docs/03-system-design.md)
4. [`docs/04-sprint-plan.md`](docs/04-sprint-plan.md)
5. [`docs/05-data-model-and-api.md`](docs/05-data-model-and-api.md)
6. [`docs/06-security-and-content-policy.md`](docs/06-security-and-content-policy.md)
7. [`docs/07-open-decisions.md`](docs/07-open-decisions.md)
8. [`docs/08-testing-and-evaluation.md`](docs/08-testing-and-evaluation.md)
9. [`docs/09-delivery-status.md`](docs/09-delivery-status.md)

Codex should also read [`AGENTS.md`](AGENTS.md) before making changes. Sprint
validation evidence is recorded in [`docs/sprint4/validation-record.md`](docs/sprint4/validation-record.md).
The free local model follow-up is in
[`docs/sprint3/local-model-validation.md`](docs/sprint3/local-model-validation.md).
The latest separately verified hosted code baseline is `411a5c8`, with all four jobs
successful in [CI run 40782756288](https://github.com/emredemirbas/multimodal-rag/actions/runs/40782756288),
including the keyless walkthrough, live source filters and deleted-source chat fences. That run
does not certify subsequent code changes. Current gates and the
distinction between software tests and representative quality are in the
[delivery status](docs/09-delivery-status.md); historical records retain their
original component-level results.

## Run locally

Create the ignored local configuration once:

```bash
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Replace the placeholder `DEVELOPMENT_AUTH_TOKEN` value in `.env` with the
generated value. Also replace the example PostgreSQL and MinIO passwords.
Generate separate URL-safe values for those passwords too. Do not repeat the
copy step over an existing `.env`, rotate existing database credentials casually,
or delete data volumes to work around a startup error.
The API intentionally refuses to start when the development token is missing
or shorter than 16 characters.

Before building, run the read-only prerequisite check (Python standard library
only; no backend dependency installation needed):

```bash
python3 scripts/check_local_setup.py
```

It checks Docker/Compose availability, current-context daemon access, configured
credential-helper executables, and privately resolved base `compose.yaml` settings
for placeholders and optional-feature setup. No raw config, secrets or command
errors are printed. Exit 1 means a blocker; warnings require review but exit 0.
It never runs `sudo`, repairs permissions/configuration, starts containers, pulls
images/weights, changes `.env` or inspects application data. It is not an app-health,
registry-login, installed-model or quality check. Custom Compose override files
are not included. Shell environment variables still take precedence normally;
use `--env-file /absolute/path/to/local.env` for a deliberately different env file.

Build and start the stack:

```bash
docker compose up --build -d
docker compose ps
```

### Common local startup issues

- **`unknown flag: --build` / missing Compose:** check `docker compose version`
  in the same user/terminal. A plugin installed only for your user may be absent
  under `sudo`; do not mix configurations as a workaround.
- **Docker socket permission denied:** CLI installation alone does not grant
  daemon access. Review [Docker's Linux access instructions](https://docs.docker.com/engine/install/linux-postinstall/)
  or rootless mode. Docker-group access grants root-level privileges; never make
  the socket world-writable. Login/session changes must reach the terminal/app
  you use; a terminal opened in an existing desktop session may retain old groups.
- **`docker-credential-pass` missing:** restore the configured helper or deliberately
  review your own Docker credential settings. [Helpers must be on PATH](https://docs.docker.com/reference/cli/docker/login/#credential-stores).
  The setup checker warns without executing helpers or changing credential storage;
  a missing helper for an unrelated registry may not block this project's pulls.
  Do not paste the config or credentials into an issue.
- **The command keeps running / repeated `/health` `200 OK`:** plain
  `docker compose up --build` stays attached to long-running service logs. Healthy
  checks continue periodically; there is no final completion message to wait for.
  Use `-d` to detach, `docker compose logs --tail=50 api` to inspect, and
  `docker compose stop` to stop services without deleting volumes. Do not use
  `down -v` unless you intentionally want to erase stored project data.

### Local services

- project workspace: <http://localhost:3000/projects>
- keyless browser walkthrough: <http://localhost:3000/demo>
- API documentation: <http://localhost:8000/docs>
- API readiness: <http://localhost:8000/health/ready>
- MinIO console: <http://localhost:9001>
- PostgreSQL: `localhost:5433`

The `migrate` service runs pending SQL migrations before the API starts. Service
ports bind to `127.0.0.1` by default.

For a first try, open **Demo guide** in the app. It includes the repository-authored
[sample VTT](examples/fastapi-intro.vtt), its [MIT license](LICENSE), explicit upload
permission instructions, supported/unsupported questions, citation inspection and
confirmed cleanup. Nothing is created, uploaded or deleted automatically. It assumes
default keyless extractive/hash retrieval and changes no settings. The actual queued
uploader combines this sample into one **00:01–00:22** chunk. The guide demonstrates
the selected portfolio v1 workflow using synthetic content; it includes no real
recording and does not establish multimedia quality or full Alpha 2 approval.

The chat source filter updates from successful source-list refreshes and processing
polls without reloading or discarding your chat draft. A removed or incompatible
selected source stays explicitly unavailable rather than silently switching to all
sources. Choose another filter for a new question; an unchanged uncertain-delivery
retry retains its original source and request key. Saved citations keep their
original generation even after a replacement index is published.

`ingestion-worker` processes uploads; `scheduler` dispatches the transactional
outbox, recovers abandoned jobs and cleans artifacts. Existing passwords and
volumes are reused. MinIO is built from pinned official source because its old
registry image is unavailable; the first build can take a few minutes. A one-shot
initializer assigns only its data volume to the non-root MinIO user. This archived
CE build is for local tests, not a production storage recommendation (ADR 0012).

Project name forms retain your attempted name after returned validation/service
errors. Pending fields are locked; successful rename displays the name actually
saved by the server. If creation delivery is uncertain, refresh the project list
before trying again: project creation does not have the source-upload replay key.

In a project, choose an SRT/VTT file (UTF-8, at most 2 MB), select your rights
statement and click **Process transcript**. Work continues if you leave the page.
If upload/import delivery fails, the unchanged draft and request key stay available
for retry; the request may already have been accepted. Only confirmed acceptance
clears the form. Changing the draft starts a new request. A page reload cannot
restore a browser-selected file, so inspect sources before selecting it again.
Retry uses the retained input; correcting malformed content requires a new upload.
Reprocessing preserves the last usable generation until replacement succeeds.
Semantic processing saves each completed batch privately, continuing in bounded
deliveries until the whole generation is ready. Worker loss or explicit retry
resumes from committed progress; an in-flight, uncommitted batch may be recomputed.
Cancel keeps saved batches for retry. Reprocess starts a new generation and removes
only its superseded unfinished staging, not published evidence or old citations.
Deletion immediately removes records, then displays tracked file cleanup status.
`YOUTUBE_API_KEY` is optional, server-side, and needed only for metadata imports;
leave it empty to use uploads without external credentials or provider calls.

After a playlist metadata import, its ordered video list shows missing transcripts
and per-video progress. In **Transcript belongs to**, select the video described
by your authorized subtitle; this records your assertion rather than verifying
alignment against a video. Optional WAV has its own **Audio belongs to** selector.
At most two combined live ASR/indexing leases run per playlist by default
(`PLAYLIST_CONCURRENCY=1..4`, shared by API, ingestion and media workers). Waiting
for capacity does not consume a processing attempt, but still counts toward the
original audio's one-hour eligibility. A failed video does not discard the other indexed videos.
Retry it separately or upload corrected subtitles after its job becomes terminal.
Older metadata imports need **Reprocess source** to populate ordered entries.
Truncated snapshots are explicitly labelled. Deleting playlist metadata keeps
separately uploaded transcripts and authorized audio; pending audio continues under
its own retention policy. Deleting the project removes all of them.

Use **Chat with tutorial evidence** to ask a self-contained question, optionally
filter to one indexed source, and inspect each citation. History survives reloads.
Stopping delivery may leave a saved answer: reload history or resend the unchanged
question to replay it without another logical turn. Default answers are quoted
transcript excerpts; the optional local model explains conservatively matched
evidence. Neither mode is a general-purpose conversational tutor.
Deleting a source also removes saved turns quoting that source.
The open chat hides those whole turns as soon as deletion is confirmed or a
successful full inventory refresh shows the source is gone. Late history/delivery
responses cannot restore them. Failed inventory reads are not deletion evidence;
reprocessing still preserves old citations. Active browser delivery stops on
observed removal without claiming to cancel an already saved answer. Physical
file cleanup remains separately tracked; already received/copied data cannot be
recalled from a user's device.

In **Source management**, choose **Read transcript** on an indexed subtitle.
Browse 50 timestamped segments per page and use **Inspect evidence** for the
stable citation record. Paging retains the same generation after reprocessing;
an older-generation notice offers **Open latest published transcript** explicitly.
Reading still works when a source uses a different search index or the project is
archived. Subtitle uploads have no playable video; no playback URL is invented.

## Optional experimental local WAV transcription

Disabled by default. Only authorized WAV signed 16-bit PCM / 16 kHz / mono,
at most 20,000,000 bytes and 10 minutes. No MP3/MP4, video/frame processing,
arbitrary downloads or paid/cloud fallback. Native inference runs in <=30-second
windows in a private credential-free service, not in the API or ordinary worker.

Explicit setup downloads about 148 MB of public multilingual Whisper-base files
from a pinned revision, verifies every SHA-256 and retains only reusable weights:

```bash
docker compose build asr
docker compose --profile asr-setup run --rm --no-deps asr-model-install
docker compose --profile local-asr up -d --wait --wait-timeout 120 asr
```

Verify an **owned/authorized <=30-second** supported WAV, without printing recognized
text or storing it in application data:

```bash
docker compose --profile local-asr run --rm -T --no-deps --entrypoint python asr \
  -m app.asr.smoke --language en < /absolute/path/to/owned-probe.wav
```

Use `--language tr` or `auto` as appropriate. This only verifies the model boundary;
it does not create a project/source or replace the normal transcript upload path.
The service has no published port, app credentials or user-data mount. It denies
new sockets/outbound connections after binding its listener, uses fresh bounded
model children, and sends no audio to a cloud/paid provider. It requires Linux
seccomp support; missing isolation/weights fail closed. It is not a learner-code
sandbox. Ordinary startup and CI do not fetch Whisper weights. Existing `.env`
settings are unchanged. See [scope and follow-up](docs/sprint4/local-asr-plan.md).

After explicit weight setup, opt in and start the complete workflow:

```bash
AUDIO_UPLOAD_ENABLED=true docker compose --profile local-asr up --build -d --wait --wait-timeout 120 api frontend media-worker ingestion-worker scheduler
```

Keep your existing `local-ai` profile active too if using Ollama. To persist the
choice, set `AUDIO_UPLOAD_ENABLED=true` in the existing ignored `.env` and include
`local-asr` in its existing profiles; do not replace `.env` or change credentials.
Capability reports configuration, **not model readiness or accuracy**. Missing
weights/service fail honestly through the job's bounded retry/failure lifecycle;
there is no model download on upload and no cloud fallback. Default SRT/VTT works
without this setup. To hide/reject new WAV uploads again without deleting data:

```bash
AUDIO_UPLOAD_ENABLED=false docker compose up -d api
```

Reload an active project and use **Experimental local WAV transcription**. Select
the recording, ownership/permission statement, language and temporary-retention
acknowledgement. SRT/VTT keeps its separate 2 MB form; its limit has not increased.
Follow transcription, indexing and cleanup independently in the source list.
Stopping upload delivery or losing the connection does not guarantee job
cancellation. Refresh sources or resend the unchanged draft with the same request
key; acceptance clears the form. Once queued, use **Cancel processing** to cancel
work. New/changed draft fields create a new request key.

Optionally select a current lesson in **Audio belongs to**. This is your alignment
assertion, not verified audiovisual matching. A lesson with active ASR or indexing
cannot receive a different replacement; an unchanged same-key retry can recover
an accepted upload. Polling/metadata refresh preserves that recovery draft even if
the selected snapshot disappears. For a genuinely new upload, select a current
lesson or standalone source. Terminal replacement keeps the previous independent
source and saved citations. Reindexing or changing a metadata snapshot never
silently reassigns the original ASR provenance. See
[WAV/playlist validation](docs/sprint4/audio-playlist-validation.md).

Original processing eligibility lasts one hour including queue waiting. Success,
cancellation, permanent failure or expiry retires audio for deletion. Scheduler/
storage outages can delay physical deletion: only **Original audio deletion
confirmed** establishes completion. Failed cleanup has its own retry. Derived VTT
stays until source/project deletion. Reindexing uses that retained text, preserves
the original ASR origin and does not restore/retranscribe retired audio. A new
transcription requires a new authorized upload; no original player/download is
provided. Migrations 0010–0012 supply the existing checkpoint/media schema; the
upload boundary itself adds no migration or applied-file rewrite.

Automatic source/transcript/evidence/chat text is **not human-reviewed**. Speech,
code identifiers and timestamps may be wrong. Upload corrected authorized SRT/VTT
as a new source when necessary; this does not silently rewrite old citations.
The native authored-speech pipeline and fixed synthetic keyword diagnostic passed
in a disposable stack, but this is not representative human/technical/multilingual
or timestamp-quality approval. The earlier `endpoint` keyword failure remains a
limitation. See [upload validation](docs/sprint4/audio-upload-validation.md),
[media workflow](docs/sprint4/media-worker-plan.md) and
[inspection validation](docs/sprint4/media-inspection-validation.md).

For explicit speech-quality measurements, use the separate
[offline/native ASR evaluation guide](docs/sprint4/asr-evaluation-guide.md).
It compares operator-owned labels with word/character errors, literal technical
identifiers and timing coverage without printing transcripts or writing app data.
The included deliberately imperfect JSON example needs no model or services; it
is synthetic, not representative speech-quality evidence. WAV opt-in stays off.

## Optional local MP4/frame/OCR tool

The standalone visual command is a separate, explicit no-network tool for authorized
H.264 MP4 (<=100 MB / 10 minutes). It extracts at most 20 uniform candidates,
preserves actual timestamps, removes exact duplicate images and runs local
English/Turkish OCR. This command does not upload or publish application evidence;
the separate opt-in MP4 API/UI workflow is described below. No paid provider is used.

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps visual-inspect \
  --authorized-input --language en < /absolute/path/to/owned-tutorial.mp4
```

Use `tr` explicitly for Turkish; mixed `en+tr` has a recorded exact-term failure.
Output contains counts, hashes and processing identity, not frames/OCR text. Your
host file is untouched; only temporary container copies exist. See the
[limits, authored native test and next steps](docs/sprint4/local-visual-guide.md).
Do not add the tool profile to ordinary application startup.

A separate optional **private service boundary** now exposes the same parser to a
profile-pinned, validating worker client. `visual` (`local-visual` profile) has no
published ports, app credentials or mounts; the dedicated `visual-worker` connects
to it in the opt-in workflow below. The parser service is stateless; starting it
alone **does not enable video upload**. Exercise its real
native HTTP boundary without starting any application service:

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.http_selftest
```

See [private protocol and limits](docs/sprint4/local-visual-guide.md#private-service-boundary)
and [component validation](docs/sprint4/visual-service-validation.md).

The next private component adds migration 0013 and atomic, scoped PNG/OCR
checkpoints. An accepted complete result can be recovered after a lost job lease;
interrupted inference may still repeat. Input/actor/rights/profile, expiry and
image/text integrity are fenced, and source/project deletion removes staged bytes.
This checkpoint component alone does not enable product video ingestion or visual
retrieval. See
[checkpoint scope](docs/sprint4/visual-checkpoints-plan.md) and
[database validation](docs/sprint4/visual-checkpoints-validation.md).

The private workflow continuation (ADR 0022, migration 0014) now supplies internal
authorized MP4 registration, a dedicated `visual-worker` queue, complete-result
recovery and independently verified raw-object cleanup. Both `visual-worker` and
the credential-free native service are opt-in under `local-visual`; normal startup
is unchanged. This component initially supplied only private registration; the
current opt-in MP4 endpoint and form are described below. Extraction-stage success
means `visual_prepared` / source `metadata_ready`, not searchable
`ready`: PNG/OCR remains private, without published evidence or citations. Raw
processing expires one hour after job creation; terminal paths retire the original,
while permitted derived staging remains until source/project deletion. No paid
service is used. See [workflow and remaining gates](docs/sprint4/video-worker-plan.md)
and [validation](docs/sprint4/video-worker-validation.md).

The next inspection component (ADR 0023, migration 0015) adds an internal
`VisualGalleryRepository.enqueue` command and separate `tutorial.publish_visual`
task. It retains one selected PNG per delivery without rerunning OCR or restoring
the original. Only a complete gallery becomes readable at
`/projects/{project_id}/sources/{source_id}/frames`, linked as **View selected
frames** on retained video sources. It shows actual timestamps, literal unreviewed
OCR and processing origin; PNGs pass through a bounded authenticated API/server-only
no-store proxy. Incomplete galleries stay hidden. Gallery publication alone is
**inspection, not a search index**: sources remain `metadata_ready` until the
separate OCR index step below. The MP4 upload boundary is a separate opt-in; no
original-video playback is provided. Raw cleanup is unchanged; source/
project deletion removes selected images and all staging too. See
[retained-frame scope](docs/sprint4/visual-gallery-plan.md) and
[verification](docs/sprint4/visual-gallery-validation.md).

The next private continuation indexes retained **OCR text** (ADR 0024), not pixels
or audio. `VisualIndexRepository.enqueue` pins a complete gallery in a new index
generation; `tutorial.index_visual` runs on the ordinary ingestion queue with the
configured hash or approved local Qwen embeddings. Eight-document checkpoints,
bounded continuations and atomic activation preserve prior evidence on failure.
Blank OCR produces no invented evidence. Frame citations/history retain exact
point-in-time PTS, original extraction origin and protected supporting-frame links.
The gallery now reports active OCR index generation/space separately; mismatched
spaces remain excluded from search. Reindexing is still an internal operator
command; public video reprocess is unavailable and uploads require the separate
opt-in below. OCR indexing alone does not add image-model descriptions or certify
OCR accuracy or full Alpha 2. See the
[index scope](docs/sprint4/visual-index-plan.md) and
[verification](docs/sprint4/visual-index-validation.md).

Private registration can now opt into `auto_process=True` (ADR 0025, migration
0017). Extraction completion atomically queues retained-frame adoption; gallery
completion atomically queues the OCR index. Both handoffs use the existing scoped
outbox, preserve the original actor and use the embedding space pinned at input
acceptance, even if the visual worker has a different default. Existing manual
mode is unchanged. Cancel stops the current stage; original-initiator derived
retry does not re-fetch raw video or rerun OCR. Already accepted work continues
through archive, which is not cancellation. Public MP4 upload and its raw-cleanup
UI were deferred to the opt-in boundary below. See [workflow scope](docs/sprint4/video-workflow-plan.md) and
[verification](docs/sprint4/video-workflow-validation.md).

The opt-in native smoke accepts only a test-authored MP4 on stdin and creates and
removes its own new development project. It requires running visual/ingestion
workers, scheduler, API, frontend, backend dependencies, and explicit matching
development credentials/ports in the environment; it never reads `.env` or runs
migrations. CI runs it on its disposable stack with hash/extractive providers:

```bash
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.http_selftest --fixture | \
  VIDEO_WORKFLOW_SMOKE=1 PYTHONPATH=backend python scripts/smoke_video_workflow.py
```

This authored-card smoke demonstrates actual queue/native/application wiring,
not representative OCR accuracy or original-video playback.

### Experimental standalone MP4 upload (off by default)

ADR 0026 connects that workflow through authenticated
`GET /api/v1/ingestion/video-capabilities`,
`POST /api/v1/projects/{project_id}/sources/video`, and a same-origin browser form.
The existing WAV capability/flag is independent. Explicitly build/start the private
visual service and worker and opt in; for a one-command local opt-in:

```bash
VIDEO_UPLOAD_ENABLED=true docker compose --profile local-visual up --build -d \
  api frontend scheduler ingestion-worker visual-worker
```

Only that command receives the override. `.env.example` keeps the default false;
later Compose commands without an explicit override or configured flag may disable
it again. No weights, paid API or arbitrary video downloader are required. Building
the isolated parser explicitly installs the documented small public OCR assets.
Configuration availability is not service readiness or a quality certification.

The form requires rights, explicit English/Turkish/experimental combined OCR, and
permission to retain selected frames/literal OCR until source/project deletion.
MP4 <=100 MB/10 minutes, H.264/avc1 yuv420p <=1080p/60fps, zero-based/unrotated only.
Optional AAC is ignored. No sound transcription, original-video player, scene
detector or playlist association is provided by this upload. Image-model
descriptions require their [separate opt-in](docs/sprint4/frame-descriptions.md). OCR can be wrong,
especially code/symbols and combined language, and uniform sampling can miss changes.

Actual multipart wire bytes/time/part counts are bounded; one video delivery per
server process prevents unbounded concurrent large buffering. API tmpfs is bounded
at 256 MiB to fit a 100 MB spooled upload without changing other upload limits.
Stopping delivery is not job cancellation: keep the unchanged draft/key for an
uncertain retry, or refresh sources to find an accepted job. Current-stage recovery
and exact frame citations use the existing atomic workflow. Raw-video expiry is
not physical deletion; source cards show pending/failed/confirmed cleanup and keep
polling after indexing. Retired original extraction requires a fresh upload;
derived retry uses retained work. Complete deletion still covers all artifacts.
See [scope](docs/sprint4/video-upload-plan.md) and
[validation](docs/sprint4/video-upload-validation.md).

On a disposable opted-in stack, add `VIDEO_UPLOAD_SMOKE=1` and
`VIDEO_UPLOAD_LARGE_SMOKE=1` to the authored native smoke above (alongside its
required `VIDEO_WORKFLOW_SMOKE=1`). This exercises production BFF/API/SSR, actual
OCR/citations/retention, a 100,000,000-byte MP4 and owned-project cleanup. CI uses
that explicit opt-in only on its fresh stack. It does not enable the owner's app.

### Inspect frames alongside a transcript

When both sources are published in the same project, open **View selected frames
→ Align with a transcript**. Choose a transcript of the same recording, confirm
that assertion and set a whole-millisecond offset (normally 0). A positive offset
looks later in the transcript. The page pins both published generations, shows
actual frame/OCR beside overlapping transcript excerpts and links to stable full
evidence. Missing spans and shortened excerpts are explicit; nearby cues are not
substituted. Old pinned views survive transcript reprocessing.

This is read-only temporal inspection, not automatic audiovisual verification,
semantic agreement, a combined citation or a saved source relationship. No model
call, playable original or default/media setting changes. See
[timeline behavior and validation](docs/sprint4/timeline-alignment.md).

### Measure OCR and retained-frame coverage

An explicit local operator evaluator accepts labels bound to an exact supported
MP4. It reports missed labeled time intervals, normalized word/character errors,
case-sensitive literal character errors, technical identifiers and unexpected OCR
on blank views. No application data access, text/frame export, model download or
paid call. Sampling coverage is not scene recall; every sampled frame is scored,
and poor measurements do not automatically enable uploads or approve quality.
See the [offline/native evaluation guide](docs/sprint4/visual-evaluation-guide.md)
and [separate validation record](docs/sprint4/visual-evaluation-validation.md).

An additional [isolated change-candidate experiment](docs/sprint4/scene-selection-guide.md)
compares a one-second thumbnail scan against the actual current uniform pipeline
on an authored transient view. The experiment itself does not change the app's sampling/profile,
stored evidence or upload defaults; no representative scene/code-quality claim.

The following [versioned selection-manifest component](docs/sprint4/selection-manifest-plan.md)
(ADR 0027, migration 0018) preserves all bounded scan scores/hashes, revalidates
ranking, protects temporal-return timestamps and keeps legacy checkpoint digests
unchanged. Gallery/citation contracts distinguish v1/v2 provenance without exposing
private scan records. Its native integration now offers experimental
`VISUAL_SELECTION=change` (ADR 0028); **uniform remains default**. See the
[change-aware OCR guide](docs/sprint4/change-ocr-guide.md) for operator CLI,
managed opt-in, pinned-job recovery and limitations. Actual fractional-PTS and
authored upload-to-citation checks are not representative scene/code quality.

The [paired code/terminal diagnostics](docs/sprint4/code-policy-evaluation-guide.md)
compare both policies on the same labeled input and separately measure identical
shared frames. Five reproducible authored probes retain trade-offs: change mode
finds a transient terminal error but misses a one-digit edit that uniform sees;
both miss the sub-second view, and cursor motion uses the change budget. No default
or quality threshold was changed; see the separate validation record.

## Optional real local AI (no API key or service bill)

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3:4b
ANSWER_PROVIDER=ollama docker compose --profile local-ai up -d api
```

Explicit setup downloads the official model (about 2.5 GB) and an Ollama image;
allow roughly 10 GB extra disk and a 16 GB-RAM machine for this CPU profile.
It uses local CPU/RAM/electricity, not a paid API. Cloud is disabled, the model port
is not published, and no credential is required. Questions never download weights.
The adapter has a one-call capacity gate and a 24-second deadline; retry if the
machine is busy. It unloads the model after each answer to limit idle RAM and
transient prompt retention. Weights remain in the `ollama_data` volume.

In the default retrieval mode, search is hash/lexical, not learned semantic. Questions need
matching identifiers/terms: weak matches abstain before invoking the model and
are labelled `local-evidence-policy`, not falsely attributed to Qwen. Generated
answers use only retrieved citation IDs, but reasoning can still be wrong;
inspect the evidence. Saved history is not implicit context. ASR is a separate
explicit WAV opt-in; MP4/OCR and local image descriptions also require their
separate opt-in setup described above.

Return to the lightweight demo without editing credentials:

```bash
ANSWER_PROVIDER=extractive EMBEDDING_PROVIDER=hash docker compose up -d api ingestion-worker scheduler
docker compose stop ollama
```

After setup, test the real model with an owned temporary project:

```bash
set -a
source .env
set +a
python3 scripts/smoke_local_model.py
```

### Optional local semantic search

```bash
docker compose --profile local-ai up --build -d ollama
docker compose exec ollama ollama pull qwen3-embedding:0.6b
EMBEDDING_PROVIDER=ollama ANSWER_PROVIDER=ollama docker compose --profile local-ai up --build -d api ingestion-worker scheduler frontend
```

This explicit download adds about 639 MB of public weights. Queries and uploads
never pull models. The approved manifest is pinned in the application; a different
manifest fails safely rather than corrupting an index. Keep API and worker on the
same `EMBEDDING_PROVIDER`. To persist the choice across normal Compose startup,
set `EMBEDDING_PROVIDER=ollama` and `ANSWER_PROVIDER=ollama` in your ignored `.env`;
do not copy the example over an existing configuration or change credentials.

For existing sources, use **Reprocess source**, wait for success and reload the
workspace. Validation-only sources without jobs need a fresh transcript upload.
The UI labels incompatible indexes and excludes them from search. Old saved
citations remain inspectable; failed reprocessing does not remove prior evidence.
Switching back to hash also requires explicit reprocessing for current search.

Search uses an English query instruction, exact project-filtered 1024-D vectors,
full-text candidates and a small identifier boost. The experimental raw-cosine
0.40 guard is not a confidence/faithfulness score: valid paraphrases may still be
rejected, and related-but-unsupported questions can still require model abstention.
This is not a broad model-quality certification. Source IDs/generations are always
validated. `ANSWER_PROVIDER=extractive` can use the same semantic index while
returning only literal evidence quotes without running the answer model.

CPU safety limits: eight chunks/batch, at most eight batches/64 segments per
delivery, no new inference after 48 seconds (existing 90/120-second task limits).
Unfinished work requeues after two seconds without consuming a failure retry;
the 2 MB / 20,000 cues / 10,000 chunks input bounds remain. A separate processing
delivery count and saved/total progress are shown in the UI. Target model space
and a chunk manifest are pinned: restore the original mode/parser to retry, or
Reprocess source after a configuration change. Queries retain six-second inference
and a shared 28-second retrieval/answer budget (answer inference at most 24 seconds).
The model receives the time remaining after query retrieval. Unknown usage stays null; local
token/model/space attribution is recorded and billed API cost is zero.

With semantic mode enabled, run the explicit owned-project probe:

```bash
set -a
source .env
set +a
python3 scripts/smoke_semantic_search.py
# Explicit 129-chunk, multi-delivery native worker/model probe:
python3 scripts/smoke_semantic_search.py --long
```

For default regression smoke scripts below, use hash/extractive mode. CI exercises
fake local embedding HTTP and real database/worker recovery, without model downloads.

Stop the stack without deleting data:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the
local data volumes. Optional model weights also live in a named volume;
`docker compose --profile local-ai down` stops the optional model container too.

## Authentication boundary

The local Compose stack uses a single development principal authenticated by the
server-side `DEVELOPMENT_AUTH_TOKEN`. The Next.js server forwards that token to
the API; it is never placed in a `NEXT_PUBLIC_*` variable or accepted from a
browser-controlled tenant selector.

`X-Tenant-ID` is no longer trusted. Direct local API requests require:

```bash
set -a
source .env
set +a
curl -H "Authorization: Bearer $DEVELOPMENT_AUTH_TOKEN" \
  http://localhost:8000/api/v1/projects
```

A trusted identity-gateway adapter is also available for later deployment
integration. Its trust and networking requirements are documented in
[`ADR 0011`](docs/adrs/0011-sprint1-identity-adapters.md).

## Test

Backend unit, API, authentication, lifecycle, and isolation tests:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=. pytest -m "not integration"
```

With the Compose PostgreSQL service running, exercise real migrations, pgvector,
project deletion cascades, audit events, and the base job schema:

```bash
cd backend
set -a
source ../.env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=. pytest -m integration --tb=short
```

Frontend checks:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Exercise the running Compose application with a disposable test project:

```bash
set -a
source .env
set +a
python3 scripts/smoke_sprint1.py
python3 scripts/smoke_sprint2.py
python3 scripts/smoke_sprint3.py
python3 scripts/smoke_transcript_viewer.py
```

Smoke checks verify project lifecycle plus actual queued upload/indexing,
reprocessing, safe failure/retry, citations and complete artifact cleanup of their
own temporary projects. The process-death integration test owns an isolated DB
schema, Redis key prefix and Celery process; it never kills the normal worker or
flushes shared Redis. CI runs these against its ephemeral Compose stack.

The transcript-viewer smoke also runs in optional semantic mode: it uses the
configured ingestion worker but makes no answer-generation calls. It verifies
53 segments across two pages, production SSR, escaped text, preserved generations,
archive reads and its own full cleanup. See
[`docs/sprint3/transcript-viewer-validation.md`](docs/sprint3/transcript-viewer-validation.md).

Record synthetic retrieval measurements from the repository root:

```bash
PYTHONPATH=backend python3 scripts/evaluate_rag.py
# With local PostgreSQL credentials exported:
PYTHONPATH=backend python3 scripts/evaluate_rag.py --postgres
```

The 19-question synthetic set is a regression check, not an independent,
provider-backed model-quality benchmark or Alpha 1 approval.

Resumable-indexing design and validation are in
[`docs/sprint3/resumable-indexing-plan.md`](docs/sprint3/resumable-indexing-plan.md)
and [`docs/sprint3/resumable-indexing-validation.md`](docs/sprint3/resumable-indexing-validation.md).
Its real-process probe kills only its own worker after a committed checkpoint,
then counts fixture embedding calls to prove no accepted batch was recomputed.
This tests recovery, not neural-model quality; native model smoke is separate.

The deterministic Sprint 0 proof remains available without Docker or model
credentials:

```bash
cd backend
PYTHONPATH=. python3 -m app.demo
```

## API

Project lifecycle:

- `POST /api/v1/projects`
- `GET /api/v1/projects?status=active|archived|all`
- `GET /api/v1/projects/{project_id}`
- `PATCH /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/archive`
- `POST /api/v1/projects/{project_id}/restore`
- `DELETE /api/v1/projects/{project_id}`

Source ingestion and recovery:

- `GET /api/v1/ingestion/capabilities` (authenticated fixed limits/opt-in flag; not model health)
- `POST /api/v1/projects/{project_id}/sources/uploads` (multipart file, rights, idempotency key)
- `POST /api/v1/projects/{project_id}/sources/audio` (experimental opt-in; multipart WAV, rights, language, key and retention acknowledgement)
- `POST /api/v1/projects/{project_id}/sources` (allowlisted YouTube metadata only)
- `GET /api/v1/projects/{project_id}/sources`
- `GET /api/v1/projects/{project_id}/sources/{source_id}`
- `GET /api/v1/projects/{project_id}/jobs/{job_id}`
- `POST /api/v1/projects/{project_id}/sources/{source_id}/retry|cancel|reprocess`
- `DELETE /api/v1/projects/{project_id}/sources/{source_id}` (`202` cleanup ticket)
- `GET /api/v1/projects/{project_id}/cleanup/{cleanup_id}`
- `POST /api/v1/projects/{project_id}/cleanup/{cleanup_id}/retry`

Deprecated Sprint 0 validation compatibility endpoint (development/test hash mode only;
the product UI uses queued uploads):

- `POST /api/v1/projects/{project_id}/sources/transcripts`

Chat and evidence (PostgreSQL required):

- `POST /api/v1/projects/{project_id}/conversations` (title and idempotency key)
- `GET /api/v1/projects/{project_id}/conversations`
- `GET /api/v1/projects/{project_id}/conversations/{conversation_id}`
- `POST /api/v1/projects/{project_id}/conversations/{conversation_id}/messages` (question, source IDs, key; SSE)
- `GET /api/v1/projects/{project_id}/evidence/{segment_id}`
- `GET /api/v1/projects/{project_id}/sources/{source_id}/transcript` (published segments; optional `generation`, fixed 50/page; pages after 1 require a generation)
- `POST /api/v1/projects/{project_id}/questions` (stateless JSON answer, optional source IDs)

Operational endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health` (compatibility alias)
- `GET /metrics`
- `GET /api/v1/runtime` (authenticated mode/index configuration, no secrets)

Every project-owned repository operation is scoped by tenant and project. An
unknown, deleted, or differently scoped project returns the same safe `404`
shape.

## Selected portfolio v1 boundary

- Python backend programming tutorials
- User-owned, authorized, or appropriately licensed SRT/VTT uploads
- Queued processing with visible progress and recovery controls
- Project-scoped hybrid retrieval and default keyless extractive answers
- Saved conversations, stable timestamp citations and versioned transcript inspection
- Private single-user projects with tenant/project isolation and complete deletion
- Reproducible local Docker Compose setup and the licensed synthetic demo guide

The finite acceptance checklist and current completion state are in
[delivery status](docs/09-delivery-status.md). Optional local answers/embeddings,
WAV transcription, MP4/OCR, image descriptions and timeline inspection remain
available as experimental extensions; v1 does not require their enablement or
claim representative media/model quality. Independent real-video review remains
open before full Sprint 4/Alpha 2 approval.

The original [sprint roadmap](docs/04-sprint-plan.md) retains generated coding
assignments, ZIP/file submissions, a hardened deterministic runner, rubric
feedback, progressive hints and the learning loop after v1. Completing v1 does not
automatically begin those later sprints.

## Core stack

- Frontend: Next.js / React / TypeScript
- API: FastAPI / Python / Pydantic
- Database: PostgreSQL, pgvector, and PostgreSQL full-text search
- Background work: Celery / Redis with PostgreSQL state, outbox and fenced leases
- Object storage: S3-compatible storage; MinIO locally
- Packaging: Docker and Docker Compose
- Untrusted code: a dedicated hardened runner in Sprint 6, not the API or normal
  worker containers

## Content constraint

Do not design the product around silently downloading arbitrary public YouTube
audiovisual content. Supported processing starts from uploaded, user-owned,
authorized, or appropriately licensed inputs. Public URLs may supply allowlisted
metadata but are not a license to download or retain media.
