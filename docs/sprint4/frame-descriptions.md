# Opt-in local image-model descriptions

Date: 2026-10-28. ADR 0029. This closes the software description slice, not the
independent real-example quality/audiovisual gate or all of Alpha 2.

## Behavior and boundaries

From a complete selected-frame gallery, **Inspect or generate local descriptions**
opens a read-only description page. The generation button requires explicit
operator setup; it is disabled by default, independently of video upload and
change-aware selection. No video is re-read or re-decoded. No audio, transcript,
OCR, filename, account/project identifier, credential or external URL is sent to
the model. A fixed image-only prompt treats visible instructions as untrusted.

The single approved provider is local Ollama `qwen3.5:4b` with an explicitly pinned
full manifest digest. Inspect capability/family, exact tag/digest and local engine
before and after inference; reject drift, remote models, proxies and redirects.
There is no pull endpoint, paid/cloud fallback, model bundled in images or model
installation performed by an API/job. The existing optional credential-free
Ollama process owns native inference. Application credentials remain in the API/
orchestrating worker boundary, never the model prompt/service.

Output is strict JSON: view kind, summary (360 Unicode code points), up to four
100-character details, up to two 100-character uncertainties and coherent
abstention. Reject unknown fields, control/surrogate characters, malformed,
truncated/tool-bearing output, invalid usage counts and image-byte mismatches.
Non-abstained descriptions remain **unreviewed model interpretations**, not
verified facts, exact code, executable instructions, speech or semantic alignment.
Preserve model uncertainty and poor outputs honestly; validation is not truth
checking. The UI escapes output and presents literal OCR separately.

## Setup — explicit operator action, not part of a default start

Keep `FRAME_DESCRIPTIONS_ENABLED=false` unless suitable local hardware and an
explicitly installed vision-capable `qwen3.5:4b` are available in the **Compose
Ollama model store**. A host Ollama installation and the Compose volume are
different stores; an existing host model does not silently make Compose ready.
Installing/importing model weights is a separate operator decision, may use
several GB of disk/RAM and is never executed automatically by this project.
See the [model documentation](https://ollama.com/library/qwen3.5:4b).

Use the local `/api/tags` response's full 64-character digest, not the shortened
`ollama list` ID or a current registry assumption. A read-only inventory, once the
operator has started their local Ollama service, can be obtained with:

```bash
docker compose --profile local-ai --profile local-vision run --rm --no-deps -T \
  --entrypoint python description-worker -c \
  'import json,urllib.request; print(json.load(urllib.request.urlopen("http://ollama:11434/api/tags",timeout=3)))'
```

Review that exact model's local identity/capabilities. Then deliberately set the
ignored `.env` values (never commit local credentials/settings):

```dotenv
FRAME_DESCRIPTIONS_ENABLED=true
VISION_MODEL_DIGEST=<full digest of the explicitly installed local model>
```

After reviewing/applying the additive migrations through the normal migration
service, deliberately build/start both profiles:

```bash
docker compose --profile local-ai --profile local-vision up --build -d
```

The native MP4 path additionally needs its existing `local-visual` profile and
independent `VIDEO_UPLOAD_ENABLED` opt-in; existing retained galleries need no
original video. No setup command above installs weights. Enabled means configured
availability, not model readiness/quality. Missing/changed weights fail the job
honestly. The local model service is shared with optional text answers/embeddings;
contention can produce retryable timeouts. Defaults remain hash/extractive.
Disabling the flag stops new requests, not already accepted jobs; use the scoped
project cancellation control to stop accepted work.

## Jobs, versions and recovery

- Authenticated, tenant/project/source-scoped `GET .../sources/{source}/descriptions`
  returns configured availability, latest job, last complete snapshot and its
  index job. `POST` with a `SourceCommand` idempotency key queues `visual_describe`.
  The original gallery initiator is required; an archived project cannot enqueue.
  Reads are private/no-store/nosniff; raw object keys and lease data are not public.
- Pin gallery, actor, model digest, prompt/schema and embedding target at acceptance;
  pin engine identity before first inference. Dedicated `descriptions` queue,
  concurrency one. One retained PNG per delivery, at most 20 frames, 600,000 bytes
  each and 960×540. Request 120s; task soft/hard 180/210s, lease 240s, visibility
  300s; output 512 tokens, context 4096. Existing input/native limits unchanged.
- Object/model I/O holds no project DB lock. Recheck actor membership, exact live
  job/generation/lease, cancellation and deletion before accepting each result.
  Save exact frame/image digest, structured output digest and identity digest.
  Partial checkpoints stay private. Durable continuation does not spend failure
  attempts; cancellation/retry reuse accepted checkpoints. A saved final frame can
  finish after worker loss without constructing/invoking a model again.
- Only complete descriptions publish. The same transaction records one usage
  event and queues existing text indexing. Old OCR evidence stays active until the
  **complete new index** commits. Failures do not erase it; older complete
  descriptions remain inspectable while newer work is incomplete.
- Migration `0019` adds scoped description runs/checkpoints/FKs and usage columns.
  Existing applied migrations `0001`–`0018` are unchanged. Parser
  `visual-evidence-chunks-v2:gN` has at most 300 chunks: separately prefixed
  `Unreviewed OCR text:` and `Unreviewed image-model description:` at immutable
  frame PTS. Abstained descriptions add no text. Old v1 OCR IDs/text/digests and
  saved citations/history remain unchanged. Mixed-index provenance pins the whole
  description run plus original extraction; labels identify each segment kind.
- Usage records image count/bytes, reported nullable input/output tokens, local
  latency, model/digest/prompt and zero billed API cost (not zero electricity or
  hardware cost). Content-free checkpoint/continuation/completion logs and existing
  processing/attempt/queue metrics expose progress. Complete source/project
  deletion cascades runs, checkpoints, indexes, vectors, usage and all retained
  frame objects; description generation creates no extra object copy.

## Validation and limits

Software checks cover actual local HTTP transport, provider readiness/drift,
strict bounds/abstention, scoped concurrent receipt replay, immutable acceptance
pins, private checkpoints, cancellation during model I/O, revoked/expired/stale
workers, corrupted result/identity/image checkpoints, atomic mixed publication,
retrieval/evidence/history, old citations, usage exactly once and complete cleanup.
A separate real Celery/Redis/MinIO/PostgreSQL SIGKILL test terminates only an owned
test worker after its final result commit: replacement finishes without a second
model call or duplicate index handoff. Model output there is an explicit fixture,
not native quality evidence. Frontend checks cover safe contracts/actions, loading,
busy/disabled/failed/empty/abstained states, escaping and provenance.

An initial prompt-candidate native model probe reused pre-existing **read-only** public
host weights (digest
`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`),
Q4_K_M, with Ollama 0.40.3 in a new internal-only container, no app credentials or
downloads. A fixed authored 320×160 two-box/arrow diagram produced a coherent
structured result in 28,407 ms (169 input/170 output tokens). It also contained
awkward/incomplete phrasing and a Chinese character despite English instructions.
Those failures are preserved, not scored as quality approval; this candidate
diagram result does not certify the final prompt. Initial test setup
attempts failed before inference (internal network without a published port,
missing client Python path, then a read-only metadata root); final setup used
read-only blobs/manifests with a small disposable metadata tmpfs. No owner service,
configuration or model store was modified.

The optional `FRAME_DESCRIPTION_SMOKE=1` extension to
`scripts/smoke_video_workflow.py` verifies native descriptions after the existing
public upload/native OCR/gallery path, production description/evidence pages,
automatic mixed indexing/citations, old evidence, zero-cost usage and complete
owned-project deletion. It requires explicitly supplied model setup and never
pulls weights. Default CI builds the worker and tests fixtures without weights.

Two fresh native card workflows initially failed closed: the model returned
`abstained=true`/`kind=unclear` but a nonempty summary, violating the existing
abstention contract. No invalid description was indexed; owned projects/objects
were still deleted. A credential-free standalone diagnostic on the original
authored card confirmed this exact inconsistency. Keep the validator and bounds;
clarify the unpublished v1 prompt's abstention instructions and remove the leading
"tutorial frame" context. No silent response repair, truncation or inference retry.

With the final prompt, the same 960×540 authored HEALTH CHECK card passed strict
validation in 52,848 ms (712 input/168 output tokens). Its summary omitted CHECK,
called the type both monospaced and sans-serif, and speculated that it was a crop.
These are known semantic failures, not quality success. A **fresh whole-stack**
native run then passed: public upload -> isolated MP4 OCR -> gallery -> two actual
vision calls through the dedicated queue -> complete description page/production
SSR -> automatic v2 index -> versioned mixed citations/evidence -> old citation
inspection -> full project/object cleanup. A second fresh owned project verified
the original change-aware six-frame/timeline workflow without extra model calls.
The model service had only an internal network, read-only pre-existing public
blobs/manifests and disposable metadata tmpfs; all new containers/networks/nonexternal
volumes were removed. No owner `.env`, application DB, service or model store was
changed; no weights were downloaded. Browser inspection also confirmed the gallery
link, disabled-while-busy button, one-of-two saved progress and hidden partials.

Final local regression: **969 backend tests passed, zero skipped**, split into
571 non-integration tests (8.48s) and all 398 integration tests (198.62s). The latter
includes actual Redis/MinIO/PostgreSQL and owned worker SIGKILL probes, including
the new final-description checkpoint recovery. All services used fresh random
ports/credentials and no owner application volumes. A final targeted image-only
test also passed: blank OCR can index/retrieve a non-abstained description without
inventing speech or OCR text. Frontend: **233 tests in 39 files**, final 8.73s;
typecheck, lint and production Docker build passed. API and dedicated description
worker image targets and the exact new CI opt-in/configuration assertion passed.
Staged secret/old-migration checks and whitespace validation passed.

Retain failed validation history honestly: the new HTTP test exposed generic
source-command route shadowing, corrected by registering the explicit description
POST first. Initial migration-list assertions needed the new 0019 filename; old
published data/checksums were then verified unchanged. An initial combined run had
967 passes and that stale-list failure; another combined run terminated with
SIGTERM and is not counted as a pass. Only its three verified disposable service
containers were removed. A later integration run had 396 passes and one existing
gallery-worker recovery timeout; both old/new worker tests then passed unchanged
in isolation (6.26s), followed by the final complete 398-test green integration
run above. No timeout was raised, test disabled or failure hidden. The existing
Starlette/httpx test-client deprecation warning remains visible. Hosted baseline
`d3c2f2b` has four green jobs in run 40581184918; these subsequent changes need
their own hosted run after push.

### Hosted CI configuration correction (2026-10-28)

The exact description commit `b594890` passed the backend unit, backend integration
and frontend jobs in [run 40589057804](https://github.com/emredemirbas/multimodal-rag/actions/runs/40589057804),
but its images job failed in the real worker/checkpoint integration step:
`test_killed_last_frame_worker_resumes_without_repeat_model_call_or_duplicate_handoff`
raised `KeyError: TEST_REDIS_URL`. That optional override existed in the local
disposable-service harness, but CI uses the Compose host port configuration.
The other worker probes already support that environment. This was a test setup
defect, not a model, image build, application migration or frontend failure.

Match the established test configuration: use explicit `TEST_REDIS_URL` when
provided; otherwise use loopback `REDIS_PORT`, default 6380. Three connection-free
regressions cover explicit-URL precedence, a custom port with no URL, and both
settings absent. Reproducing CI locally with the URL removed and only a **new
disposable Redis's random port** failed before the fix, then all four checks in
the corrected worker test file passed (3.15s), including actual owned-process
SIGKILL/recovery, no repeated model call, usage once, one index handoff and cleanup.
No existing application service was used. No test skipped, deadline increased,
assertion weakened, dependency changed or model downloaded. Application code,
schema, owner `.env` and upload/model opt-ins are unchanged.

The corrective commit `f99b86a8042138a4fd507cfda9fef6086c56c911` was subsequently
verified in [run 40593035299](https://github.com/emredemirbas/multimodal-rag/actions/runs/40593035299):
backend-tests, backend-integration, frontend and images all completed successfully,
including the actual worker/checkpoint recovery step that previously failed.
This is the green code baseline, not a claim that the earlier `b594890` run passed
or that model quality has been accepted.

Independent review on owned/licensed real audiovisual examples and a recorded
human acceptance decision remain the last full Sprint 4 gate. Synthetic cards,
this native diagram, schema checks and passing test counts do not close it.
