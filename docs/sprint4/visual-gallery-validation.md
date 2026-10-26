# Retained-frame adoption and inspection validation

Date: 2026-10-26. Scope: ADR 0023 / migration 0015. This completes selected-frame
adoption/inspection, not visual indexing/citations, public MP4 upload or Alpha 2.

## Software checks

The complete backend regression runs in new disposable PostgreSQL/pgvector, Redis
and MinIO containers with tmpfs data, test-only allowlisted credentials and
`TEST_REAL_WORKER=1`; no actual `.env`, application DB/bucket/queue or volume.
Final result: **570 passed, no skips, 118.17 seconds**. One upstream TestClient
deprecation warning is reported; no check is disabled. Only exact newly created
service IDs are removed afterwards; the owner's stack is unchanged.

New coverage includes 33 gallery DB/coordinator/API cases, an actual post-PUT
worker SIGKILL and a real HTTP test of the exact configured Compose health command:

- Concurrent idempotent enqueue and duplicate delivery accept one publication/
  frame; unprepared/foreign scope cannot queue or expose results. Full composite
  origin/source/generation FKs reject a different source's existing visual run.
- One PNG per delivery, 20 maximum including entirely blank OCR, continuations
  without a failure attempt, and zero partial gallery/image visibility. Only a
  fully verified set becomes readable. No content_segments, processing_versions
  or active index generation is created; answers still abstain.
- Retained actual PTS, literal hostile OCR and engine/language/profile origin
  survive a new publication generation. Unknown model time/tokens are not invented:
  copying adds processing-attempt duration/aggregate metrics, not inference usage.
- Derived work can continue after confirmed raw deletion and expired original
  eligibility. Cancel/retry reuses accepted frames, never recreating an original.
  Tenant/project/source/generation/token/initiator mismatches, revocation, actual
  wall-clock lease loss after PUT and deletion fail closed.
- Unique orphan reservations survive rollback; delayed failed-candidate cleanup
  cannot delete later accepted PNGs. Manifest/text/hash/profile/missing-row/key/
  object corruption is rejected. Source/project deletion covers every private row
  and original/adopted/candidate object.
- Protected no-store JSON/PNG reads, bounded PNG integrity checks, post-storage
  reauthorization and archived inspection. Existing tenant-membership read policy
  is preserved; only the original initiator can request the private adoption job.
  No original key/digest, object URL or private incomplete result is projected.

Frontend: **26 files / 130 tests pass**, lint/typecheck and the five actual lint
compatibility cases pass. Repeated in an ephemeral **Node 24.21.0** builder with
network disabled and no app credentials/mounts; production Next.js build passes.
New cases cover strict origin/manifest/source contracts, Unicode OCR bounds,
literal hostile text, loading/empty/image-error/retry, scoped page/not-found/safe
error, correct source navigation and no unusable raw-video reprocess control.
PNG proxy tests verify server-only upstream credentials, no redirects, actual
streamed-byte overflow despite a false header, MIME/signature/length rejection,
deadline, no-store/nosniff/same-origin headers and pre-forward cross-site/invalid-ID
rejection. Full npm audit reports **zero vulnerabilities**. The first audit could
not resolve npm inside the sandbox; the normal-network repeat succeeds, not an
ignored advisory. No dependency/version or audit threshold changed.

## Actual process loss / MinIO evidence

Only a test-owned Celery solo process and isolated schema/Redis prefix/queue are
used. The prepared extraction is explicitly a synthetic fixture, not native OCR.
Pause immediately after real MinIO PUT, before frame adoption; SIGKILL only that
owned process. No retained frame row is committed, but its separate orphan ticket
survives. Verified cleanup removes only the failed candidate. After lease recovery,
a replacement uses two deliveries to adopt two PNGs and publish the gallery.
Provider construction is forbidden throughout. The observed totals are three PUTs
(one orphan, two retained), three deliveries/two attempts, one original extraction
usage event and no extra work on a completed duplicate. PNG content type and actual
reads/bytes pass. Complete project cleanup leaves no object in its owned prefix.
This tests delivery/adoption recovery, not prefork signal enforcement or exactly-
once inference. Existing native/task budgets are unchanged.

## Combined native production workflow

A separate UUID-named disposable Compose project uses fresh data volumes/networks,
test-only credentials and `--env-file /dev/null`, loopback-random ports, separately
tagged current API/worker/frontend images and the existing minimal native image.
No app/model-data volumes or actual `.env` are mounted. Native visual service stays
credential-free/internal-only/read-only/resource-bounded with inherited kernel/
child socket denial; only the trusted worker spans the two networks.

The first attempts exposed an actual **Compose healthcheck incompatibility**:
urllib sends User-Agent, rejected by the intentionally narrow private header
allowlist. The service itself was ready, but Compose blocked the worker as unhealthy.
Replace only the health command with `LocalVisualClient(...).ready()`, keeping the
protocol allowlist intact. A unit test executes the exact configured command over
real loopback HTTP. CI now explicitly starts/waits for optional visual service and
worker, then includes them in its own project cleanup. Failed disposable attempts
are removed; they are not counted as passed native workflows.

The final fresh-stack run passes:

1. Actual Compose service and worker health; migration 0015 in the **test DB only**.
2. Generate the same authored high-contrast MP4 cards using the isolated native
   fixture generator. Register through the private authorized Python repository,
   not an MP4 API/form. Real scheduler/outbox/Celery/native FFmpeg/Tesseract produces
   `visual_prepared` with one native extraction event.
3. The private gallery enqueue triggers actual separate publication deliveries:
   two retained PNGs, one logical publication attempt and two deliveries; actual
   PTS `[0,10000]` and the pre-existing explicit Turkish card diagnostic pass.
4. Production Next SSR renders unreviewed-OCR/not-indexed guidance, exact timestamps
   and retained-frame links. The actual server-only image proxy returns the same
   verified PNG bytes with no-store/same-origin headers. Unauthenticated API image
   read returns 401; same-tenant foreign-project read returns 404.
5. Raw input has confirmed `deleted_at` and only two selected-frame objects remain.
   Gallery reads/adoption do not increment native extraction count (still one).
6. Delete only the owned test project through the real API, await its cleanup
   ticket, verify empty MinIO prefix and old-frame 404, then remove only the exact
   validated disposable Compose project's containers/networks/volumes.

This is actual combined native workflow/production SSR/BFF evidence, separately
from fixture-backed process-loss tests. It is still only authored synthetic cards:
`quality_approval=not_established`. It does not resolve the known combined-language
Turkish diagnostic failure or establish scene/code/terminal/representative OCR
quality, long-video performance or general speech transcription.

## Delivery and remaining scope

Prior migrations 0001–0014 are unchanged. Existing user services/data/configuration
and weights remain intact; no app migration, restart or opt-in flag change. Hosted
CI must be verified for the actual pushed commit, not inferred from local tests.
Public MP4 upload, retained-OCR indexing/stable visual answer citations and reviewed
scene/OCR evaluation remain separate follow-ups. A retained gallery is not `ready`
search evidence, an original-video player or a full multimodal milestone.
