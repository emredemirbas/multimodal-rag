# Opt-in managed change-aware OCR producer

Date: 2026-10-27. Continue ADR 0027's existing v2 contract; no new data schema.

## Scope and assumptions

Keep uniform v1 as the default and preserve pinned existing jobs. Offer the fixed
experimental `change` selection explicitly through `VISUAL_SELECTION` on the
trusted visual worker only. The credential-free native service supports both
fixed profiles through a narrowly validated selection query; no app identity,
secret, arbitrary expression, URL, filesystem path or environment reaches it.
Upload opt-in flags and the owner's running stack/.env/data are unchanged.

Reuse the existing bounded thumbnail scanner and full manifest. Decode selected
full-size frames in one second pass using fixed integer-millisecond PTS matching,
not a rounded seek that could substitute the next source frame. Require exact
selected/result PTS equality, reject missing/extra/duplicate outputs, preserve
temporal returns and apply existing bounded literal OCR. Validate the complete
v2 result before delivery. Keep all current media, CPU/wall/PID/file/tmpfs/network
limits; complex accepted clips may still time out. No new model or paid fallback.

Pin the configured selection at the first native identity/checkpoint, as with
the existing engine/language pin. A new configuration affects only unpinned jobs;
retry/resume restores its stored identity and never migrates an old generation.
Do not silently fall back to uniform when a change service/profile fails.

## Verification

Cover native coordination/strict output/deadline/privacy failures, policy/query/
readiness/body/profile pairing, default compatibility, both directions of pinned
job recovery after configuration drift, existing authorization/deletion fences and
configuration isolation. Run actual no-network native transient/return OCR and
fractional-FPS PTS probes, then an owned disposable API/BFF -> Celery -> native
v2 -> gallery/index/citation/SSR -> confirmed original/project cleanup workflow.
CI should exercise both fixed policies explicitly without changing normal defaults.

Quality remains experimental: the authored view is not a representative code,
scene or OCR benchmark. One-second thumbnails can miss brief/small edits and spend
the budget on irrelevant motion. No vision descriptions, verified audiovisual
alignment, new formats/retention or full Sprint 4/Alpha 2 claim.
