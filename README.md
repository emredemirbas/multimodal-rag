# Multimodal RAG

[![CI](https://github.com/emredemirbas/multimodal-rag/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/emredemirbas/multimodal-rag/actions/workflows/ci.yml)

A local workspace for turning programming tutorials into searchable material with
inspectable evidence. Upload authorized transcripts, ask questions within a
project, and follow answers back to timestamped source segments.

The default setup runs without API keys or model downloads. It combines lexical
search and deterministic hash vectors with extractive answers. Optional local
models add answer generation and semantic embeddings; experimental media workflows
add speech transcription, selected video frames, OCR and image descriptions.

## Features

- **Project workspaces:** create, rename, archive and delete private projects.
- **Transcript ingestion:** upload SRT/VTT files, follow queued processing, and
  retry, cancel or reprocess sources.
- **Evidence-backed chat:** filter questions by source, save conversations, and
  inspect stable citations tied to a processing generation and timestamp.
- **Transcript browsing:** read published segments chronologically without making
  a model request.
- **Playlist organization:** import official YouTube metadata and associate your
  own authorized transcripts with individual lessons.
- **Recoverable processing:** durable jobs, checkpointed indexing and atomic
  publication preserve usable evidence while replacement work is in progress.
- **Scoped data and cleanup:** tenant/project boundaries apply to retrieval,
  history and artifacts; source and project deletion track object cleanup.

Optional workflows are disabled by default:

| Capability | Local implementation |
| --- | --- |
| Generated answers | Ollama with Qwen3 4B |
| Semantic retrieval | Qwen3 Embedding 0.6B in a separate, versioned index space |
| Speech transcription | Isolated Whisper-base service for restricted WAV inputs |
| Video evidence | Isolated FFmpeg/Tesseract processing, selected-frame gallery and OCR citations |
| Image descriptions | Explicitly pinned Qwen3.5 vision model with separately labelled output |

See [local development](docs/local-development.md) for setup, limits and recovery.

## Quickstart

Install Docker with Compose and Python 3, then clone the repository:

```bash
git clone https://github.com/emredemirbas/multimodal-rag.git
cd multimodal-rag
```

Create a local configuration only if one does not already exist:

```bash
if [ ! -e .env ]; then
  cp .env.example .env
  chmod 600 .env
fi
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

For a new setup, replace the example `DEVELOPMENT_AUTH_TOKEN`, PostgreSQL password
and MinIO password in `.env` with separate generated values. The auth token must
have at least 16 characters. Keep an existing configuration and database credentials
when resuming a setup; `.env` is ignored by Git.

Check prerequisites, then build and start the stack:

```bash
python3 scripts/check_local_setup.py
docker compose up --build -d
docker compose ps
```

The checker is read-only. It checks Docker/Compose access and configuration without
starting services, downloading models or printing secrets. First startup builds
images and runs database migrations; it needs network access for dependencies.

Open the [workspace](http://localhost:3000/projects) or the
[demo guide](http://localhost:3000/demo). The
[API reference](http://localhost:8000/docs) is available locally as well.
Ports bind to `127.0.0.1` by default.

For startup problems, additional ports and configuration details, see
[the local setup guide](docs/local-development.md#setup-and-services).

## Try it

1. Create a project.
2. Upload the repository's [sample VTT](examples/fastapi-intro.vtt), selecting its
   appropriate rights statement. The sample is synthetic and covered by the
   repository's [MIT license](LICENSE).
3. Wait for processing to finish, then ask a self-contained question such as
   “What does the health endpoint return?”
4. Open the answer's citation to inspect its source text, timestamp and processing
   version, or choose **Read transcript** to browse the source directly.
5. Delete the test source or project when finished and follow the cleanup status.

The in-app demo guide includes supported and unsupported example questions and
cleanup instructions. It does not upload or delete anything automatically.

Default answers quote matched evidence. Use terms present in the transcript;
weak or unsupported matches can abstain. Optional local generation still requires
evidence inspection, and saved chat history is not implicit model context.

## Architecture

The application is a modular monolith with separate runtime processes:

```text
Next.js web → FastAPI API → PostgreSQL + pgvector
                  │                 │
                  ├── S3 objects    └── transactional outbox
                  │                           │
                  └── Redis / Celery ← scheduler
                            │
                     ingestion workers
                            │
                  optional local model/media services
```

- **Web:** Next.js, React and TypeScript.
- **API:** FastAPI and Pydantic.
- **Search:** PostgreSQL full-text search and exact, project-filtered vectors.
- **Jobs:** Celery/Redis with PostgreSQL state, fenced leases and checkpoints.
- **Storage:** S3-compatible objects, with MinIO in the local Compose stack.

Model adapters belong to the application; evidence records retain model, prompt
and processing identities where applicable. See the
[system design](docs/03-system-design.md) and [architecture decisions](docs/adrs).

## Development

Backend checks, after installing the editable development package in a virtual
environment:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=. pytest -m "not integration"
```

Frontend checks (Node.js 20.19 or later):

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

The [development guide](docs/local-development.md#testing) covers integration
services, disposable smoke checks, local-model setup and API usage.

## Constraints

- Process only uploaded, owned, authorized or appropriately licensed material.
  YouTube URL imports fetch allowlisted metadata, not audiovisual content.
- The default hash/extractive mode is a reproducible baseline, with limited
  paraphrase understanding. Optional model output can contain errors.
- WAV/MP4 and image descriptions are experimental opt-ins. Generated transcripts,
  OCR and descriptions are unreviewed; representative audiovisual quality has not
  been established. Video uploads do not provide original-media playback.
- The Compose authentication adapter is intended for a private local user.
  The stack is not configured as a public hosted service.
- Assignment generation is under development and is not available in the
  workspace. Solution uploads and code assessment are not implemented.

## Documentation

- [Local setup, optional capabilities, tests and API](docs/local-development.md)
- [Product brief](docs/01-product-brief.md)
- [Requirements](docs/02-requirements.md)
- [System design](docs/03-system-design.md)
- [Data model and API design](docs/05-data-model-and-api.md)
- [Security and content policy](docs/06-security-and-content-policy.md)
- [Testing and evaluation](docs/08-testing-and-evaluation.md)

## License

[MIT](LICENSE). Uploaded content and optional model weights retain their own
licenses and usage conditions.
