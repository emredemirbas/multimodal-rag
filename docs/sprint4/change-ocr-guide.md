# Experimental change-aware frame/OCR selection

Real managed v2 OCR is available; **uniform remains default**. No paid provider,
weight download, new format/retention or automatic old-source reprocessing.
Existing media/security limits remain in `local-visual-guide.md`.

## Single-clip operator diagnostic

```bash
docker compose build visual-inspect
docker compose --profile visual-tools run --rm -T --no-deps visual-inspect \
  --authorized-input --language en --selection change \
  < /absolute/path/to/owned-tutorial.mp4
```

Without `--selection`, the command remains uniform v1. Output is content-free
metadata, never OCR/PNG payloads; hashes can still identify private input. Existing
explicit `--reference` diagnostics accept v2 too, without approving quality.

## Managed opt-in

Follow existing MP4 upload/local-visual setup first, including migration 0018.
This feature adds no migration and does not enable `VIDEO_UPLOAD_ENABLED` or WAV.

```bash
VISUAL_SELECTION=change docker compose --profile local-visual up --build -d visual-worker
```

This is an explicit operator service update, not something the assistant ran on
the owner's stack. Only the trusted worker receives this setting; the native
container has no environment/credentials. Keep `.env.example` default uniform.

Selection is pinned at first checkpoint initialization, **not upload acceptance**.
Changing the worker default affects unpinned jobs only. Incomplete/saved retries
restore their pinned v1/v2 identity; completed sources/citations never convert.
Reindexing OCR does not repeat selection. After original cleanup, another extraction
needs a new authorized upload/key. Restore the unpinned default with:

```bash
VISUAL_SELECTION=uniform docker compose --profile local-visual up --build -d visual-worker
```

There is no uniform fallback on change-profile failure and no per-upload UI policy
selector. Galleries/citations show the actual pinned origin and limitations.

## Actual authored native probe

```bash
docker compose --profile visual-tools run --rm -T --no-deps --entrypoint python \
  visual-inspect -m app.vision.change_selftest
```

It checks private HTTP/OCR, temporal returns and exact PTS at 2, 30000/1001 and
1001/1000 fps, also verifying encoded FPS. No application records. CI separately
tests public upload -> native v2 -> gallery/index -> cited transient/SSR ->
confirmed original/project cleanup. See `change-ocr-validation.md`.

At most 600 small thumbnails and 20 selected points; no inferred visible durations.
One-second/downscaled scans can miss brief/small edits or rank cursor motion highly.
Nearby frames are not substituted. Unchanged native limits can reject complex
clips even within 100 MB/10-minute input bounds; this is not a performance promise
or representative scene/code-quality result.
