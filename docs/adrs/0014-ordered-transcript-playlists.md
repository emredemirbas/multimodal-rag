# ADR 0014: Ordered playlist snapshots and bounded subtitle processing

- Status: Accepted for the authorized transcript-first Sprint 4 slice
- Date: 2026-10-11

## Decision

Persist immutable metadata generations in `playlist_items`, with both tenant and
project scope on every key/query/relationship. Keep the official provider's
playlist-item identity separate from the video identity: a video can occur more
than once. Preserve its zero-based position rather than silently renumbering gaps.
Only the last successfully committed snapshot is shown. Duplicate item identities
or positions and invalid responses fail safely without replacing that snapshot.

A refreshed snapshot carries an existing upload only if both item and video
identities match; reordering does not change that upload's original provenance.
Previously saved citations still resolve to their unchanged transcript generation.
Old pre-migration metadata requires a successful reprocess to populate ordered
relationships, since its cached JSON did not retain provider playlist-item IDs.
The existing 100-item/three-page limits and explicit truncation remain in place;
do not describe a truncated snapshot as a full import.

An upload may specify a current `playlist_item_id`. Under the project lock,
validate its scope and current snapshot before object adoption, bind the source,
and create its job/outbox atomically. Include the item in the idempotency hash;
standalone hashes remain backward-compatible. Uploads retain an independent rights
assertion and `user_asserted` video alignment, not verified audiovisual alignment.
Replacing a linked upload is allowed only after its previous job becomes terminal;
the old independent source and evidence are not implicitly deleted.

At claim time the same project lock fences a maximum of two live transcript leases
per parent playlist. `PLAYLIST_CONCURRENCY` can set a local safety limit of 1–4.
A job without a free slot remains pending/retrying at `waiting_capacity`, consumes
no attempt, and requeues through the outbox with a two-second delay. Clearing the
outbox publication lease prevents a racing dispatcher acknowledgement from hiding
that redelivery. Normal per-source retry/cancel/lease recovery remains authoritative.
These are application guarantees, not assumptions about Celery exactly-once work.

Bounded operational metrics expose waiting job count without content/ID labels;
existing attempt/usage rows retain scoped provider, duration and zero-cost offline
attribution. Metadata is not searchable tutorial evidence. No paid models, video
or caption download, binary-media retention or new network destination is enabled.

Deletion of a transcript nulls its playlist relationships in every snapshot and
removes derived cited chat as before. Deletion of playlist metadata cascades its
snapshots but only unlinks independent uploaded transcripts; the UI confirmation
explains that they remain. Deletion of the entire project still removes all rows,
embeddings and objects using the existing durable cleanup workflow.

## Release boundary

This is the ordered-transcript slice, not full multimodal Sprint 4/Alpha 2 approval.
FFmpeg, ASR, scene selection, OCR/vision, frame alignment and visual evaluation still
require their own decisions and implementation. Live YouTube metadata requires an
owner-configured server-side API key and has not been inferred from synthetic tests.
Provider-backed Alpha 1 and independently reviewed quality gates remain open.

## Authorized WAV follow-up (2026-10-23)

The ADR 0020 opt-in WAV route now accepts the same optional current
`playlist_item_id`. It binds the pending audio source before ASR, then keeps that
identity through retained-VTT adoption and indexing. The existing relationship
column `transcript_source_id` also represents this pending authorized audio; only
indexed complete transcripts count as evidence. Preserve audio metadata when
adding the user-asserted association; do not replace it with playlist metadata.
Standalone request hashes remain byte-compatible; only selected items extend them.

The project-locked `PLAYLIST_CONCURRENCY` cap now counts **combined live ASR and
transcript-indexing leases**, not independent per-queue budgets. All relevant
Compose processes receive the same value. Waiting/continuations do not consume
failure retries, and raw eligibility still expires one hour after registration.
Existing scoped snapshot carry-forward, busy replacement, metadata unlinking and
independent-source deletion behavior applies to WAV too. No new schema or broader
media permission. Native/fixture verification and limitations are recorded in
`../sprint4/audio-playlist-validation.md`.

References: [official playlist item resource](https://developers.google.com/youtube/v3/docs/playlistItems),
[PostgreSQL 16 scoped foreign-key deletion actions](https://www.postgresql.org/docs/16/ddl-constraints.html).
