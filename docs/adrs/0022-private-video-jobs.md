# ADR 0022: Private local MP4 jobs and original retirement

- Status: Accepted implementation of ADR 0021's authorized follow-up
- Date: 2026-10-26

Use a dedicated trusted Celery visual worker for scoped coordination, never native
decoding in the API/ordinary/audio worker. It alone joins the credential-free
parser's internal network. Keep normal startup/product video upload disabled.

Bound one whole extraction delivery with 180/210-second soft/hard limits and a
240-second lease. Existing WAV limits remain unchanged. Configure visual broker
visibility 300 seconds; the existing shared Redis 240-second shorter value also
exceeds the hard task limit. Database state/outbox, not Redis messages, own recovery.

Register private authorized MP4 through a committed orphan reservation and bounded
PUT, then atomically adopt source/job/input/outbox after rechecking authorization.
Pin full engine/language-data identity before inference and retain completed
checkpoints across lease recovery without another provider request. Lost in-flight
inference can repeat. No exactly-once or per-frame resume guarantee is implied.

Finish this slice at `visual_prepared`, not published ready. Verify saved PNG/OCR
under the live fence, atomically record completion/actual accepted counts/zero
billed local usage and retire raw input. Retain permitted private derived results,
but no content_segments/processing_versions, active generation or public evidence.
Final object adoption/indexing and UI remain required before video enablement.

Raw eligibility is fixed at one hour from job creation. Retirement on all terminal
paths, expiry and revocation creates independent scoped cleanup tickets. Mark raw
deletion only after verified storage cleanup, preserving failure/retry visibility.
Terminal retry cannot recreate an original. Source/project deletion removes raw
objects, checkpoint metadata/bytes/text and usage through existing complete cleanup.

See `../sprint4/video-worker-plan.md`. Primary references:
[Celery time limits](https://docs.celeryq.dev/en/stable/userguide/workers.html#time-limits),
[Redis visibility and shared brokers](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html#visibility-timeout).
