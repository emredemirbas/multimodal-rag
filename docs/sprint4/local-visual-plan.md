# Local MP4/frame/OCR foundation

Date: 2026-10-26
Status: Implemented and locally validated; private stateless component only,
not product video ingestion. See `local-visual-validation.md`.

## Owner direction and bounded decisions

After the concrete MP4/OCR/retention proposal, the owner delegated the technical
choices ("kafana göre yap"). Proceed with owned/authorized uploads only, <=100 MB /
10 minutes, <=20 selected frames, local English/Turkish OCR and no paid/cloud
fallback or arbitrary downloading. Future product originals retire on success,
cancellation or permanent failure and expire for processing after one hour;
physical cleanup must remain separately observable. Permitted selected frames and
OCR may remain until complete source/project deletion. Default capability stays
closed until durable jobs, cleanup, provenance and accessible UI are connected.

The first implementation intentionally narrows MP4 to one H.264/avc1 8-bit
yuv420p video, <=1920x1080, 1–60 fps and a zero-based timeline. Optional AAC audio
is ignored, not decoded or transcribed. Other codecs, fragmented containers,
rotation, non-zero starts and malformed timelines fail honestly. New WAV limits
and application upload APIs are unchanged.

## This slice

- Bounded standard-library top-level MP4 box inspection before native processes.
- Separate explicit, credential-free, non-root/read-only, no-network Compose
  tool; no database/object/queue/user-directory/Docker-socket mounts. Reuse the
  existing inherited fail-closed kernel network filter before any native decoder.
- Fresh filtered resource-limited children for FFprobe, FFmpeg and Tesseract;
  fixed commands, forced MOV demuxer, file/pipe protocols only, external data
  references disabled, finite input/output/process/CPU/wall limits. Input and
  decoded intermediates live only in bounded temporary container storage.
- Up to 20 uniformly spaced candidates (one per five seconds for short clips),
  actual decoded millisecond PTS, fit within 960x540 grayscale, exact decoded-pixel
  deduplication and deterministic PNG encoding. This is **not scene detection**
  or approximate visual deduplication; small code changes must not be erased by
  a perceptual-similarity assumption.
- Application-owned typed interface with image/input hashes, engine/language-data
  identities and processing profile, literal untrusted OCR and actual timestamps.
  No visual descriptions/vision LLM, video/audio association or published evidence.
- Explicit stdin smoke command, rights acknowledgement and content-free summary;
  no frame/text export or automatic model download at request time. Build-time
  Debian OCR language packages are public local assets, not hosted inference.

## Verification and follow-up

Unit tests cover malformed containers/metadata, timestamps, image/PNG integrity,
exact deduplication, strict output, bounds, timeout/group cleanup and credential
filtering. Run authored native English/Turkish cards in new disposable no-network
containers; report OCR failures separately from component/software success. Add
the optional image/build/native smoke to CI without changing normal startup.

No migration is needed for a stateless tool. Dedicated authorized video jobs,
leases/checkpoints, actor/tenant/project fences, complete raw/derived cleanup,
stored processing identities, source UI, visual retrieval/citations and reviewed
scene/OCR quality remain required before enabling product video ingestion. Do not
claim full Sprint 4/Alpha 2 completion or use this decoder as a learner-code runner.
