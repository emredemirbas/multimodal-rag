# Explicit change-aware frame candidate experiment

This operator-only prototype does not change application uploads, managed visual
profiles, checkpoints or citations. It proposes <=20 actual PTS points, not OCR/
frames stored in the application. No vision model, paid service or download at
inference. Keep private input outside the checkout and do not publish its hashes.

## Run the authored comparison

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.scene_selftest
```

This generates a fixed 20-second video with a brief view at `[3000,4000)` ms,
compares the **actual current uniform/OCR pipeline** with the new thumbnail scan,
and tests the real operator CLI plus safe malformed-input rejection. It creates
no application records or objects. The current baseline retains PTS `[0]` after
exact deduplication; the prototype selects `[0,3000,4000,7000,13000,19000]` on the
authored constant-2fps fixture. Do not extrapolate this to real code or scene recall.

## Inspect an owned/authorized supported clip

```bash
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.scene --authorized-input \
  < /absolute/path/to/owned-tutorial.mp4
```

All earlier input restrictions remain: <=100 MB / 600s, non-fragmented zero-based
unrotated H.264/avc1/yuv420p MP4, <=1080p / constant 1–60fps, optional AAC ignored.
No URL/playlist download, audio transcription or broader native format support.
The tool uses the existing no-network/non-root/read-only/tmpfs/resource/child
restrictions and takes bytes only on stdin. No app credentials, directories or
Docker socket are mounted. Your host file is not deleted. Native temporary files
disappear with the owned temporary context/container; there is no image/text exporter.

## What selection means

The source is scanned with at least one-second spacing at <=160x90 grayscale,
at most 600 thumbnails. The fixed `select` filter retains source PTS rather than
inventing a one-FPS timeline. Validate first PTS, constant geometry, source-FPS-
bounded gaps and coverage through the end; incomplete output fails rather than
publishing a partial proposal. Existing native CPU/wall limits are **not increased**:
large/complex clips may time out even within accepted byte/duration limits. The
maximum bounds have unit coverage, not a new native 10-minute performance result.

Compare adjacent thumbnails. A pixel counts as changed at >=24 gray levels;
>=2,000 changed pixels per million (0.2%) makes a point eligible. Ranking uses
changed-pixel fraction, then mean absolute difference, then earlier PTS. These
constants are an experimental noise/budget policy, not reviewed quality thresholds.

Up to four anchors cover the start, thirds and nearest final sampled point,
choosing nearest actual PTS with earlier ties. Highest-ranked eligible changes
fill the remaining 20-point budget. Static views therefore need not fill all 20
points. The report counts omitted eligible changes. Repeated pixels after a scene
return can remain as another point: matching an earlier image does not establish
continuous visibility. No duration is inferred from one timestamp.

Reports contain input/thumbnail SHA-256, video metadata, actual selected PTS,
anchor/change flags, counts/scores and a separate versioned engine/policy/profile.
They contain no pixels, OCR, filename or raw native exception. Fingerprints are
still sensitive for private input. `quality_approval` is always `not_established`;
ordinary completion means the bounded experiment ran, not that scenes were found
correctly or OCR/semantic search improved.

One-second spacing can miss sub-second views. Downscaling can erase small code
edits; cursor motion, fades, animation, compression and lighting can rank highly.
Do not use this heuristic to remove code evidence globally or call it a vision
description/semantic scene detector. Technical-identifier and representative
visual labels still require separate review.

## Prototype boundary and managed follow-up

This profile deliberately cannot be parsed as an existing `VisualIdentity` and
produces no `WireResult`. Do not label these points with the old uniform policy,
alter old checkpoints, or assume the source list is already using this algorithm.
Managed integration needs its separately versioned/persisted manifest, legacy
compatibility, worker/auth/retry/deletion coverage and truthful UI/provenance;
those are not claims made by this standalone experiment.
See `scene-selection-plan.md` and `scene-selection-validation.md`.

The subsequent storage/contract component is documented in
`selection-manifest-plan.md` (ADR 0027, migration 0018). It prepares a distinct
managed v2 result and persists/revalidates its full bounded scan manifest, with
legacy-digest tests and gallery/index/citation version support. This standalone
CLI still emits only its original prototype report. The separate ADR 0028 native
producer now delivers v2 OCR with explicit `VISUAL_SELECTION=change`; ordinary
defaults remain uniform. See `change-ocr-guide.md` and its validation record.
