# Machine-generated evidence and original-audio inspection

Date: 2026-10-23
Status: Implemented and locally validated; see `media-inspection-validation.md`.
Public WAV upload remains disabled.

Continue ADR 0019 in a small read-only delivery slice before enabling uploads.
No provider, media format, retention permission or paid dependency changes.

- Expose a typed ASR origin on source inventory, published transcript pages,
  evidence inspection and answer citations. Resolve evidence through the selected
  processing generation's scoped ASR-run FK, never mutable source metadata or the
  currently active generation. Reindexing must retain the original ASR identity.
- Expose temporary-original eligibility and confirmed cleanup separately. Expiry
  and retirement do not prove physical deletion. Pending/failed cleanup remains
  visible, with the existing authorized cleanup retry boundary for failed work.
- Label automatic transcripts as not human-reviewed. Explain potential speech,
  code-identifier and timestamp errors, corrected subtitle upload, and the
  distinction between reindexing a VTT and transcribing audio again. Do not invent
  a player or an accuracy certification; retain the prior native probe limitation.
- Keep read paths tenant/project scoped, bounded and free of model/object reads,
  secrets, object keys or raw provider payloads. Use existing relational links;
  no schema change or migration rewrite is needed.
- Cover source/adoption/reindex provenance, old citations/history, ordinary and
  legacy subtitles, cleanup expiry/failure/retry/completion, authorization and
  source/project deletion. Verify strict frontend contracts, accessible states,
  literal untrusted text and no regression to SRT/VTT behavior.

Public authenticated WAV API/BFF/form, upload-wire bounds and the separate owned-
audio native end-to-end check remain the next enablement slice. This inspection
work does not open an upload endpoint or imply that those gates have passed.
