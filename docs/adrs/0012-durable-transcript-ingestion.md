# ADR 0012: Durable transcript ingestion, provenance and artifact cleanup

- Status: Accepted for the authorized Sprint 2 implementation
- Date: 2026-10-02

## Decision

PostgreSQL owns source/job state. API registration stores a source, its retained
SRT/VTT artifact reference, a job and an outbox event in one transaction. Redis
and Celery provide at-least-once delivery, not domain state or exactly-once work.
Task arguments contain scoped IDs and a generation only. Workers recheck live
project state and the initiating user's membership before reading/committing.

An API-generated source prefix gets a separately committed cleanup reservation
before object PUT. A bounded PUT occurs while the registration transaction holds
the project and reservation locks. Adoption removes that reservation in the same
commit as registration. Rollback leaves it due immediately; process/DB loss leaves
it due after fifteen minutes. This closes object/DB and deletion/adoption gaps
without assuming a distributed S3/PostgreSQL transaction.

Uploads are UTF-8/UTF-8-BOM SRT/VTT, at most 2,000,000 bytes, with an explicit
rights assertion. Raw transcripts have `permitted_transcript` retention until
source/project deletion. This does not grant binary-media retention permission.
The wire-body bounds at FastAPI and Next.js allow an additional 16 KiB for form
envelopes. Initial safety caps are 200 sources/project, 20,000 cues/input, 10,000
chunks/input, 1,200 characters/chunk and 60 seconds/cue or chunk. Sentence endings
and eight-second timeline gaps supply deterministic section boundaries; this is
not a claim of model-based topic classification.

Worker claims carry a token and a 180-second lease, longer than the 90/120-second
soft/hard limits. Redis visibility is 240 seconds. Attempts are bounded at three
per automatic run, with capped backoff/jitter; explicit retry permits at most
twelve total attempts on one job. Cancellation invalidates the claim immediately.
The scheduler recovers expired claims, retries outbox publication and redelivers
unclaimed jobs. Duplicate messages cannot change a completed generation.

Stable segment IDs include source, generation, parser version, chunk ordinal,
original cue range/timestamps and a normalized-content hash. A successful commit
atomically activates the new generation. Older segment/version records remain
unchanged until source/project deletion. Failed/cancelled replacement never
removes the last successfully indexed evidence. Processing/provider/model,
dimensions, attempts, duration and zero-billed deterministic usage are persisted.

Deletion commits a minimal cleanup ticket before relational cascades. The ticket
has no project/source FK, contains no user content, and is readable only by its
authenticated initiating tenant/user under the original project scope. Source
deletion returns `202`; project deletion retains `204` with `X-Cleanup-ID` and a
`Location` status URL. Relational inaccessibility is immediate; object deletion is
scheduled, verified and retried up to six times. Failed cleanup can be explicitly
retried. A stale worker cannot recreate rows or objects. Queued ID-only messages
are harmless delivery hints and are discarded when consumed against deleted
records; shared queues are never purged to delete one project.

## Metadata and local storage

YouTube adapters accept canonical HTTPS video/playlist IDs, never arbitrary
fetch URLs. Only fixed official Data API endpoints are requested; redirects are
rejected. Requests have five-second timeouts, 1 MB response bounds and at most
three pages/100 playlist items with explicit truncation. Metadata-only sources
are not retrieval evidence and request an authorized transcript separately.
Missing `YOUTUBE_API_KEY` fails registration honestly; no audiovisual/caption
downloader, live provider test or binary-media processor is introduced.

The first hosted CI failed while pulling the old MinIO image. Upstream now
distributes CE as source and its repository is archived. Local/CI builds therefore
compile official commit `7aac2a2c5b7c882e68c1ce017d8256be2feea27f` with pinned Go,
retain its AGPL license and run the server non-root. A one-shot, volume-only
permission migration assigns existing MinIO data to UID 1000; it does not delete
data. This is a development/testing dependency, not a production storage
recommendation. Production uses an application-owned S3 interface and requires
a maintained storage service and backup/retention review before beta.

## Consequences and evidence

Registration briefly holds a project lock during bounded storage I/O. Very large
uploads, hosted authentication, quotas/billing, binary media and provider-backed
embedding quality require their own milestones. Exact project-filtered retrieval
remains the baseline; no HNSW or chat feature is added.

See `docs/sprint2/validation-record.md`. The process-death test owns an isolated
PostgreSQL schema and unique Redis namespace; it kills only its own Celery process,
advances only its own DB lease, then verifies a replacement worker and duplicate
delivery. It never stops the user's Compose worker or flushes shared Redis.

References: [Celery task acknowledgements](https://docs.celeryq.dev/en/stable/userguide/tasks.html),
[Redis visibility timeout](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html),
[official MinIO source/status](https://github.com/minio/minio),
[video metadata](https://developers.google.com/youtube/v3/docs/videos/list),
[playlist items](https://developers.google.com/youtube/v3/docs/playlistItems/list).
