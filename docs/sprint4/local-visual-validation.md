# Local visual component validation

Date: 2026-10-26
Status: Local software and isolated native component/explicit-language checks pass.
The combined-language Turkish diagnostic **fails** and remains a known limitation.
Hosted CI is separate and not claimed as passed in this pre-push record. No full
multimodal/Alpha 2 or representative OCR/scene quality approval.

## Delivered and software evidence

- Strict top-level non-fragmented MP4 bounds, fixed native codec/timeline subset,
  <=20 uniform candidates, actual PTS, bounded grayscale pixels, deterministic PNG,
  exact-image deduplication, literal OCR and hashed engine/language-data profile.
- Explicit standalone no-network Compose tool; no API/ordinary worker decoder,
  database/object/queue credentials, application mounts or automatic downloads.
- Content-free authorized stdin CLI, inherited kernel socket denial and fresh
  fixed native subprocesses with filtered environment, CPU/address-space/file/
  FD/wall bounds and owned-process-group timeout cleanup.

The focused suite passes **57 cases (0.07s)**: malformed/truncated/oversized/extended
boxes, fragmented/foreign formats, duplicate metadata/NaN, codecs/rotation/geometry/
duration/frame rate, sample bounds, P5 geometry, PNG CRC/decompressed pixel identity,
safe literal output, exact duplicate removal while preserving single-pixel changes,
actual/mismatched timestamps even for discarded duplicates, invalid/oversized OCR,
missing isolation, language-data/version/profile drift, credential filtering, timeout
kill ownership, native exec limits and authorization acknowledgement before reads.

Final complete backend regression: **381 passed, no skips, 67.61s**, including real
PostgreSQL authorization/isolation, Redis/Celery worker-death recovery and MinIO
cleanup. Verification used only three newly created disposable loopback services,
tmpfs data and allowlisted test-only credentials. No application `.env`, service
volumes or data were used. Only exact newly returned container IDs were removed.

Compose config validates without reading `.env`: network `none`, no application
mounts/env/ports, read-only, 1 GiB RAM/no extra swap and 32 PIDs. The tool is absent
from ordinary `config --services`. Normalize numeric strings/integers in config
checks because Compose versions serialize byte limits differently. CI now builds
the optional image, verifies that config and runs the actual authored-card smoke;
existing audit/backend/frontend/ASR/application/worker checks remain intact.

## Native evidence and failed diagnostic

The minimal production visual image built successfully. It packages FFmpeg
**5.1.9-0+deb12u1**, Tesseract **5.3.0**, Pydantic **2.14.1** and local Debian OCR
language data. Observed SHA-256:

- eng: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`
- tur: `7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7`

New disposable no-network/read-only/non-root containers used 192 MiB tmpfs, 1 GiB
memory/no extra swap, two CPUs, 32 PIDs, no-new-privileges and dropped capabilities.
They had no host/app-data/credential/model-volume mounts or Docker socket. The
kernel restriction was actually inherited by a child: new socket creation failed
with EPERM. Native FFmpeg/Tesseract then ran under that same inherited restriction.

The authored high-contrast 20-second 960x540/2fps H.264 MP4 was **329,836 bytes**,
SHA-256 `683607d7a2985bf98fca722d0cc96117301d39cdbfaaf9f99862cf2814c2bbac`.
Expected cards/phrases were fixed before inference. All three requested language
modes produced four candidates, two distinct PNG frames and two exact duplicates
removed; retained actual PTS were **0 / 10,000 ms**. PNG hashes were stable:

- English card: `30e5c23ccc1e0d1d77b2fa22401aa5e9db8b2a5d3a0b499f090a9056d1f599de`
- Turkish card: `5badbe8f078998d4b84bae86ebe77c6e5a1d36ee39d8ef1f3975547096b6893d`

The initial **combined `en+tr` exact-term check failed** on the Turkish card while
English terms were found. Explicit `tr` on the unchanged clip passed the Turkish
check; explicit `en` passed the English check. Default is now explicit English,
matching the operator probe pattern; use `--language tr` for Turkish. There is no
automatic language detection/fallback. The final self-test asserts known-language
checks and reports `combined_language_turkish_exact: false` separately, preserving
the failure instead of representing it as universal multilingual recognition.

The ordinary authorized stdin command additionally passed on that authored clip,
including its optional fixed English-card check; malformed stdin exited 1 without
echoing its payload. Reports contained hashes/counts/profile and no frames/OCR or
raw exception. Temporary fixture/input/intermediates were removed with their owned
contexts/containers. These tiny artificial cards do not validate real terminals,
code punctuation/identifiers, natural slides, scene recall or long-input performance.

## Not delivered

No public MP4 API/form, source/job rows, video/ASR association, durable authorization/
checkpoints/retries, original-object retirement/cleanup, retained frame/OCR storage,
visual indexing, scene detector, visual citations or vision-description model.
Those components must retain tenant/project/actor/version fences and complete
deletion before product video enablement. The accepted future original/derived
retention policy is recorded in ADR 0021, not implemented by creating app storage.

No applied migration, existing data, shared queue/bucket, frontend dependency or
actual `.env` changed; it remains ignored/mode 0600. Application services were not
restarted. This is not a learner-code sandbox certification. See
`local-visual-guide.md` for operator use and narrower input limits.

Hosted follow-up: `7f0ee79` passed both backend jobs in
[run 40338181380](https://github.com/emredemirbas/multimodal-rag/actions/runs/40338181380)
but failed the frontend's transitive Zod dependency audit. The image/native visual
job was skipped, not passed. See `zod-security-validation.md` for the separate
targeted lockfile correction and verification.
