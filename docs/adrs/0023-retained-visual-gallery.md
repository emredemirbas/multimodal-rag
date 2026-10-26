# ADR 0023: Atomic retained-frame adoption and scoped inspection

- Status: Accepted continuation of ADRs 0021–0022
- Date: 2026-10-26

Adopt selected PNG/OCR from prepared results in a separate trusted Celery job,
one frame per bounded delivery. Keep native decoding in the credential-free
service; never re-read or recreate an original for derived adoption. Each candidate
uses a unique committed orphan reservation. Post-PUT authorization and wall-clock
lease checks precede atomic reference adoption; interrupted candidates are cleaned
without deleting another attempt's accepted object.

Retain exact input processing identity and frame/image/text/manifest relationships.
Publish a gallery marker only after complete adoption. Reads expose immutable
selected-frame IDs and processing origin, not storage keys or private staging.
Authenticated image reads verify bounded PNG bytes and recheck authorization after
storage. A server-only browser proxy sends no-store/nosniff/same-origin headers.

This is the inspection part of the visual-evidence path, not OCR indexing, scene
detection, audio transcription, playable media, public MP4 upload or full Alpha 2.
Source remains `metadata_ready` without an active retrieval generation. No token,
model-time or billed usage is fabricated for copying already accepted results.
Permitted derivatives remain until complete source/project deletion; original
expiry and separately confirmed raw cleanup are unchanged. See
`../sprint4/visual-gallery-plan.md`.
