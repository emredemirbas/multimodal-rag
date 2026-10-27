# Versioned change-selection checkpoint contract

Date: 2026-10-27. Scope: the persistence/provenance gate after the isolated
candidate prototype, not deployment of a new native sampling default.

## Assumptions and delivery

Continue Sprint 4 while the portfolio finish-line choice remains pending. Retain
the current uniform native service and all upload defaults. Add an explicitly
different managed identity (`local-visual-v2`), wire protocol and checkpoint version
for future change-aware extraction; never relabel a legacy uniform result.

The new private manifest retains all <=600 bounded thumbnail score/hash records,
geometry and selected actual PTS. Recompute the four anchors and deterministic
top-change ranking when saving/loading, checking source-FPS-bounded coverage,
score arithmetic, <=20 selected points and one exact decoded frame per selection.
It is an integrity/reproducibility record, not independent verification that a
thumbnail hash or a visual change correctly represents tutorial content. It
contains no thumbnails, OCR or inferred visible durations. Temporal returns may
repeat decoded pixels under v2 only; legacy exact-dedup requirements stay intact.

Add migration 0018 with a bounded nullable JSON column on the existing fully
tenant/project/source/job/generation-scoped run and cascading deletion. Preserve
legacy wire serialization and canonical result digests byte-for-byte. Save the
manifest in the same fenced transaction as the complete result, resume without
reselection, and reject missing/tampered/mismatched manifests. No migration is
applied to the owner's running stack as part of this work.

Propagate the new version through gallery/index/citation provenance and display
truthful selection limitations in the UI, without exposing private scan hashes or
scores. Verify legacy history, new temporal-return evidence, retry, scope,
membership/cancellation fences, corruption, deletion and upgrade compatibility.
Logs/metrics remain content-free and existing per-project attribution applies.

## Explicit remaining gate

The isolated candidate CLI still is not a managed OCR producer. The native service
and client still use uniform v1; this delivery does not make uploads scene-aware.
Next connect native scan -> bounded full-size OCR -> v2 result to an explicitly
pinned service/worker policy, then verify the actual end-to-end workflow. Native
extraction must reproduce exact selected PTS even at fractional source frame rates,
not silently substitute a nearby later frame for a rounded millisecond target.
Native budgets, credentials, network isolation and accepted media formats must not expand.
Representative scene/code quality and transcript/frame alignment remain open.
