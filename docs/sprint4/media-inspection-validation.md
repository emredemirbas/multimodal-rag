# Media provenance and original-audio inspection validation

Date: 2026-10-23
Status: Read-only inspection slice implemented and locally validated. **WAV
application upload remains disabled**. No new native ASR quality claim.

## Delivered

- Typed `asr_origin` on source inventory, published transcript pages, evidence
  inspection, stateless question citations and persisted chat/history/replay.
  Includes the original job/generation, provider/model/revision/profile/engine,
  requested language, assembly version and completion time. No original key,
  input digest, raw window output or credentials cross this projection.
- Source origin resolves through the retained artifact. Published evidence and
  citations resolve through their own processing generation's scoped ASR-run FK,
  not source metadata or the current active generation. Reindexing does not change
  the ASR generation. Legacy/ordinary subtitles have no fabricated origin; absence
  is not a statement that their text is human-reviewed or accurate.
- Typed `audio_retention` reports temporary eligibility, expired eligibility,
  pending cleanup, failed cleanup and confirmed deletion separately. Only the
  recorded successful cleanup marker establishes deletion. Status and source/job
  details share one statement snapshot. Cleanup retry uses the existing
  membership/project/actor-owned receipt boundary, not a new storage permission.
- Accessible source, transcript, evidence and chat labels identify automatic
  transcription as not human-reviewed. Speech/code/timestamp caveats, explicit
  corrected-subtitle guidance and separate reindex/retranscription meanings are
  visible. Retired raw-only sources do not advertise unusable retry/reprocess.
  No original-audio download or player is invented.
- Source polling also follows temporary/expired/pending original cleanup after
  indexing finishes, pauses while hidden and stops on confirmed deletion or a
  failed receipt. Failed cleanup has an authorized retry/error state. Existing
  manual source refresh remains available. No ASR/object read occurs on inspection.

## Checks

- Full backend on **three newly created disposable PostgreSQL/Redis/MinIO
  services: 243 passed, no skips** (60.36s), with `TEST_REAL_WORKER=1`. Includes
  actual test-owned Celery process loss/recovery and MinIO cleanup, using fixture
  inference rather than native recognition. Six new media-inspection integration
  tests cover unpublished windows, VTT adoption/index handoff, original lifecycle,
  model/version metadata drift, retained generations and citations/history,
  ordinary/legacy input, tenant/project/membership/archive/deletion, safe HTTP
  projection and authorized cleanup retry.
- Frontend **20 files / 77 tests** pass, including strict BFF round trips, malformed
  or mixed model origins, expiry-versus-deletion contracts, literal hostile text,
  source polling/visibility/stop, raw-only recovery restrictions, accessible cleanup
  retry/error and published evidence route states. Lint, typecheck and lint-adapter
  compatibility checks pass. Production Next.js build passes with normal local
  process permissions; the sandboxed attempt could not parse its TypeScript child
  process configuration. Direct `tsc --showConfig` and typecheck were successful.
- API and frontend Docker production builds also pass. A network-disabled,
  read-only ephemeral API container confirms the new schemas are packaged, no
  public audio endpoint is enabled, and `pip check` passes.
- No schema change: migrations 0001–0012 remain untouched. Inspection uses existing
  scoped artifact/version links. No new provider, weight download or paid call.
  `.env` remains unchanged, ignored and mode 0600.

## Test-environment safety and initial failed attempt

The broad run against the configured shared services was blocked by automatic
safety review because of the historical legacy-test isolation issue. It was not
retried against those services. Read-only inspection confirmed the legacy vector
test now uses its isolated fixture, all test stores derive from isolated DSNs,
and real-worker cleanup uses owned processes/prefixes rather than shared flushes.

Use fresh service containers as an additional boundary: no application `.env`,
mounts or volumes; loopback-only random ports; allowlisted child environment with
test-only credentials/DSNs; local existing images with pulls disabled; tmpfs data.
The initial 256 MB PostgreSQL tmpfs filled with WAL: 233 tests passed before a
`DiskFull` failure and dependent connection errors. Its own containers were removed.
Increase only the disposable PostgreSQL limit to 1 GB tmpfs / 1.5 GB memory, then
the full 243-test run passes. Cleanup removes only full container IDs created by
that invocation, including their disposable tmpfs data. No application services,
data, objects, queues, volumes or applied migration history were changed by these
full-suite runs. Earlier focused integration checks used existing isolated schema
fixtures with in-memory object storage, not application data.

The temporary verification driver is not shipped as a runtime dependency or an
API/worker Docker-socket integration. Existing application containers were not
restarted. Hosted CI and native owned-audio quality are separate evidence; do not
infer either from the local software tests above.

## Remaining enablement gate

Authenticated bounded WAV API/BFF/form (explicit rights/language/retention), the
separately reported owned-audio native end-to-end check, and upload/recovery/deletion
verification are still required before enabling audio uploads. The previous
synthetic native keyword-quality failure remains a limitation. Vision/OCR and
assignment/grading are not delivered by this slice.
