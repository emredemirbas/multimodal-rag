# ADR 0027: versioned change-selection checkpoint manifests

Date: 2026-10-27
Status: Accepted for the storage/contract component only; native application
selection remains uniform v1. No quality approval or new upload opt-in.

## Decision

Introduce the distinct fixed `local-visual-v2` identity, `local-visual-http-v2`
result and `visual-checkpoint-v2` for the future one-second thumbnail change
policy. Provider/engine/language-data identity remains pinned and canonically
hashed. Legacy v1 identities, serialization, digests and deduplication remain
unchanged; no existing records/citations are rewritten.

A v2 result includes `visual-change-selection-v1`: constant thumbnail geometry,
all <=600 actual-PTS score/hash records and <=20 selected PTS. Validate coverage
with the accepted source FPS, zero start, bounded ordered gaps, feasible integer
scores and exact recomputation of anchors/ranked changes. The original experiment
and validator share the deterministic ranking. Every selected point must have
one full-size PNG/OCR frame at that exact PTS. No deduplication across different
selected times: an identical view can be a temporal return, not continuous evidence.
No inferred visible intervals, perceptual code suppression or semantic description.

Migration 0018 adds a <=192 KiB nullable JSON manifest on `visual_runs`, preserving
its composite scope/FK/cascades. v1 forbids a manifest; completed v2 requires one.
The complete result digest covers every score/hash, including unselected points.
Manifest/frames/digest are written atomically under the existing membership,
actor, generation, lease, cancellation and wall-clock fences. Load/retry/gallery
revalidate the complete manifest and digest, without reselecting or fetching raw
video. A run's checkpoint version must match its pinned identity.

Gallery/index/citation origin accepts only the two matching profile/checkpoint
versions. Public projections retain the compact origin and truthful selection
notice, not private scan records/hashes. Existing usage records attribute the new
profile and selected-frame count; checkpoint logs add only the scan count.
Source/project deletion removes the manifest through the existing run cascade.

## Consequences and boundary

Scores/hashes are processing provenance, not independent proof of native pixels,
tutorial relevance or benchmark quality. Max-size validation is a bounded synthetic
storage test, not a ten-minute native performance result. Existing rights, native
resource/security limits, zero-paid-service requirement and raw/derived retention
classes remain unchanged.

The service/client configuration and native OCR producer are not switched in this
component. Actual managed scan -> selected OCR -> stored v2 evidence needs the next
explicit producer/policy integration and real end-to-end validation. Until then
ordinary uploads still produce uniform v1 results. See
`../sprint4/selection-manifest-plan.md` and its validation record.
