# Authorized WAV association with ordered playlist lessons

Date: 2026-10-23
Status: Implemented and locally verified; see `audio-playlist-validation.md`.
Continue only approved WAV/playlist scope, not video/OCR. WAV remains default-off.

The preceding upload commit `59780b6` is already pushed and all four hosted jobs
passed run `39973110441`. The next small Sprint 4 slice connects that opt-in WAV
path to ADR 0014's existing user-selected playlist relationships.

Material assumptions surfaced to the owner:

- Optional `playlist_item_id` identifies a current same-tenant/project metadata
  entry. Audio alignment is the user's assertion, not verified against downloaded
  video, original audio or timestamps. Keep a standalone choice and independent
  rights/language/temporary-retention consent. No new format/provider/retention.
- Reuse existing scoped parent/item columns and foreign keys; no schema change or
  applied migration edit. Append association to the request hash only when present,
  preserving exact standalone replay compatibility. Preserve audio metadata and
  original ASR provenance through VTT adoption, refresh, replacement and reindex.
- Existing `PLAYLIST_CONCURRENCY` (default two) bounds the **combined** live ASR and
  transcript-indexing leases of a playlist, under the existing project lock. Slot
  waiting consumes no failure attempt and uses the same fixed outbox routing.
  One-hour original eligibility still includes slot/queue waiting. This is a live-
  lease bound, not a promise of exactly-once inference or a new billing quota.
- A pending ASR or indexing job makes the linked lesson busy. Terminal replacement
  keeps the previous source/evidence. A matching refreshed item/video carries the
  link, but changing video identity must not. Deleting metadata unlinks independent
  audio/transcript sources and does not cancel them; source/project deletion still
  covers their raw/derived objects and evidence.
- Extend only the bounded authenticated audio API/BFF and gated form with one
  optional UUID. Retain exact required fields, duplicate/unknown rejection, byte/
  time/Origin/auth bounds and default-off flag. Verify the upstream association
  before returning the existing minimal browser receipt. Stable uncertain-delivery
  drafts must not silently change lesson when source polling refreshes options.
- Test concurrent binding/replay/conflict, mixed-queue slot claims/continuations,
  scope/stale/busy errors, metadata-refresh/deletion and retained provenance. Cover
  strict BFF fields/receipt and accessible standalone/selected/busy/stale/recovery
  UI states. Use disposable services, never the owner's `.env` or data volumes.
  Verify actual production BFF/native queue handoff using only authored speech and
  fixture metadata in a new disposable stack; this is not live metadata or speech
  quality certification. Keep earlier vocabulary limitations.
