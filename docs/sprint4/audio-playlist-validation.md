# WAV association and shared playlist processing validation

Date: 2026-10-23
Status: Implemented; local software and final native/runtime configuration gates
passed. WAV remains default-off; this is not full multimodal completion.

## Delivered boundary

- Optional current `playlist_item_id` on the existing authenticated bounded WAV
  API/BFF/form. Same-scope item lookup, busy replacement and link/source/job/outbox
  adoption use the existing project lock. Preserve all audio flags by merging
  association metadata. The reused pending `transcript_source_id` relationship is
  not a claim that unfinished ASR is published evidence or verified alignment.
- Append only nonempty association IDs to the upload hash; standalone requests
  retain exact prior bytes/replay behavior. A changed lesson conflicts under the
  same key. Accepted replay precedes live-item validation and still works after
  metadata refresh/deletion. New work requires a current available lesson.
- Shared per-playlist live ASR/index lease cap (default two, configured 1–4), not
  independent queue budgets. Project-lock serialization covers concurrent claims,
  normal transcript jobs, ASR continuations and downstream indexing. Waiting uses
  existing outbox routes and metrics, consumes no attempt and never extends raw
  eligibility. Compose now passes the value explicitly to the media worker too.
- Form offers standalone/current lessons, disables busy choices for new drafts,
  warns about user-asserted alignment and keeps an uncertain draft's selected item
  and key even if polling marks it busy or replaces its snapshot. Only an explicit
  user change rotates the key. Verified acceptance resets selection; BFF validates
  upstream association before stripping it to the existing minimal receipt.
- Existing snapshot carry-forward requires matching item/video identities. Old
  source/citation/ASR provenance survives terminal replacement and reindex. Metadata
  deletion explicitly keeps independent audio and does not cancel it; normal raw
  retirement and full source/project deletion remain in effect. No new provider,
  format, model download, media permission or schema/migration change.

## Software evidence

- Final full backend: **276 passed, no skips** (114.12s), including actual isolated
  worker recovery, against new disposable PG/Redis/MinIO services with test-only
  credentials/DSNs and no application `.env` or volumes. Only exact created IDs/
  tmpfs data are removed. The preceding iteration passed 275 tests before the
  explicit post-PUT association/revocation check was added.
- Eight new integration tests cover concurrent registration/idempotency/conflict,
  busy media/index handoff, retained provenance and reindex without extra fixture
  calls; unchanged standalone hashes; ten concurrent mixed claims with exactly two
  live playlist leases/eight zero-attempt waiters; standalone independence; actual
  committed ASR continuation waiting/resumption and bounded index handoff; scoped/
  stale/duplicate/malformed HTTP items; snapshot carry-forward/video changes;
  metadata unlinking, cancellation and complete source/project/orphan cleanup.
- Frontend **22 files / 104 tests**, lint/typecheck/compatibility pass on the local
  runtime. Six new BFF/form/workspace checks cover canonical optional IDs, strict
  field counts, false association receipts, detached-source deduplication, retained
  busy/stale drafts, explicit key changes, safe literal labels, standalone/terminal
  choices and honest slot/eligibility messaging. CI-pinned **Node 24.21.0** also
  passes all **104** tests, lint/typecheck and all **5** lint-compatibility checks
  in a network-disabled ephemeral builder without application data/credentials.
- Dependency audit: **zero vulnerabilities** at validation time. No dependency,
  audit threshold or workflow bypass. Production image/native results are separate
  from fixture inference; no live YouTube provider availability is implied. API,
  scheduler/migration, ingestion, media, ASR and frontend production Docker builds
  pass; the final native probe runs these images.
- Hosted image validation now also resolves Compose with a nondefault cap of one
  and checks all four application processes receive it, without starting ASR or
  downloading weights. Existing audit/tests/build/isolation/smoke checks remain.

## Native/runtime gate

Use a new UUID-named Compose project with test-only credentials, no `.env`, fresh
data volumes/networks, loopback-random web/API ports, internal-only ASR and only
preinstalled public weights shared read-only. Fixture-seed two ordered metadata
entries in that disposable database without a metadata job/API key/network call;
this is deliberately **not a live YouTube import**.

The probe rechecks production SSR/Origin and 19,200,044-byte upload/cancellation/
physical cleanup without inference. Then submit the same fixed-before-inference
authored synthetic phrase as the previous upload record (176,204-byte canonical
WAV). Verify the selected item through the real BFF, native private Whisper,
separate Celery media/index workers, source inventory/ordered progress and typed
per-version unreviewed evidence. Reindex retained VTT to generation 2; delete only
playlist metadata and replay the original request with its now-stale item ID.
Source/evidence persists, parent is null, and original ASR origin remains stable.
Count **one** native inference event through replay/reindex/metadata deletion.
Finally delete the source/project and verify empty object prefixes/404s, then
remove only that disposable stack's containers/networks/data (not external weights).

Final configuration gate: resolve the Compose environment and assert the same
nondefault `PLAYLIST_CONCURRENCY=1` on API, scheduler, ingestion and media worker;
also read Settings inside the running test media worker. The first pipeline probe
passed before that explicit media-worker configuration propagation was finalized,
so it is not evidence that a nondefault setting reached every process. Rerun the
native sequence after the propagation fix before recording the gate as passed.

**Final result: PASS.** Resolved configuration verifies one for all four processes,
and Settings in the actual test media worker reports one. The complete linked
BFF/native-Celery/VTT/index/SSR/reindex/metadata-delete/stale-replay/source-and-
project-cleanup sequence passes in the fresh stack. Exactly one native inference
event is observed; the fixed `hello`/`audio`/`health` diagnostic passes separately.
Both disposable native stacks and the backend-test services are removed afterwards.
The owner's existing application services stay healthy and public weights remain.

Synthetic keyword expectations remain `hello`, `audio`, `health`, never tuned to
output. Earlier failed `endpoint` recognition remains unresolved. Neither fixture
metadata nor synthetic speech establishes human/technical/multilingual/timestamp
quality, live metadata availability, long-ASR performance or multimodal completion.
The large silent input tests upload/cancellation, not native long-audio recognition.

## Remaining scope

Actual owner `.env`/credentials and running application services stay unchanged;
WAV still needs explicit local setup and opt-in. No application migrations are
applied by these test runs. Hosted CI must be checked independently after push.
Video, frame retention, OCR/vision and later assignment/grading work remain open.
