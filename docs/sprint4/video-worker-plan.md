# Private MP4 job and original-retirement workflow

Date: 2026-10-26
Status: Implemented and locally validated as a private prepared-only slice; ADR 0022.
See `video-worker-validation.md`. Hosted CI is reported for the pushed commit.

Continue the accepted owned/authorized <=100 MB/600-second MP4 and local OCR
scope. This slice connects private registration, object storage, durable Celery
execution and original cleanup. No public API/BFF/form, paid provider, arbitrary
URL/downloader, audio transcription or published visual evidence is added.

- Migration 0014 adds scoped temporary `video_inputs`, independently tracked raw
  cleanup and a prepared marker on existing private visual runs. Preserve 0001–0013.
- Reserve unique orphan cleanup before PUT; recheck rights/membership/project and
  reservation after PUT before atomically adopting source/job/outbox/input. Replay
  preserves the original job and never resurrects a retired original.
- A dedicated optional `visual-worker`/queue receives only scoped IDs. It has app
  credentials but no native decoder; the separate credential-free `visual` service
  alone decodes. Only this trusted worker joins both app and visual-private networks.
- Use explicit 180/210-second soft/hard task limits, 240-second DB lease and
  300-second configured visibility. Other workers retain 90/120-second limits and
  240-second visibility (shared Redis's shorter value still exceeds visual hard
  execution). One extraction per delivery, bounded failures, no provider fallback.
- Pin observed identity before extraction. Existing complete checkpoints resume
  without even contacting the model service; incomplete pins cannot auto-update.
  A lost in-flight full extraction may repeat. Save then verify the complete
  snapshot before atomically marking `visual_prepared`, recording actual accepted
  counts/processing duration with zero billed local usage and retiring the raw input.
- Prepared is **not indexed/ready**: source stays `metadata_ready`, no active
  generation, published frame/segment or visual citation. Final object adoption,
  visual indexing/evidence and UI remain separate follow-up.
- Raw processing eligibility ends one hour after job creation; retirement occurs
  on success/cancel/permanent failure/expiry/revocation. Physical deletion is only
  recorded after separately verified cleanup; failure/exhaustion stays observable
  and retryable through existing actor-owned cleanup tickets. Terminal video retry/
  reprocess requires re-upload, not raw resurrection. Complete source/project
  deletion covers objects and every private checkpoint byte.
- Test authorization, idempotency/concurrency, post-PUT revocation/orphans, original
  integrity/expiry, profile drift, retries and all terminal cleanup paths. Exercise
  an actual test-owned Celery SIGKILL after checkpoint commit with isolated Redis
  and MinIO: replacement finishes without another fixture/native call. Native
  inference/quality evidence remains separately labeled.

Do not migrate/restart the user's stack or alter `.env` as a test side effect.
Use new disposable services, schemas, buckets/queues and test-only credentials.
Normal startup excludes the optional visual profile; public MP4 upload stays closed.
