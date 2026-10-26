# ADR 0021: Isolated local MP4/frame/OCR foundation

- Status: Accepted, staged implementation
- Date: 2026-10-26

The owner delegated the choices after the proposed owned/authorized MP4, 100 MB /
10 minute, <=20 frame, local OCR and derived-retention scope. This supersedes the
earlier blanket "MP4/frame retention unapproved" statement only for this bounded
path. Paid models, arbitrary video downloading and other binary formats remain out.

First implement a separate explicit stateless FFmpeg/Tesseract tool with inherited
kernel network denial, no application credentials/mounts and bounded native child
processes. Start with H.264/avc1 yuv420p, <=1080p/60fps, zero-based MP4; ignore AAC
audio. Uniform candidates and exact decoded-pixel deduplication are transparent
baselines, not scene recall or approximate similarity claims. Return actual PTS,
PNG/input digests, OCR and engine/language-data processing identity behind an
application-owned interface. Never treat unreviewed OCR as authoritative code.

No public API, queue work, storage or database records are added by this component.
The container's temporary original/intermediates disappear on exit. Future product
ingestion must retire originals on terminal paths, enforce <=one-hour eligibility,
confirm physical cleanup independently, retain only permitted frames/OCR until
source/project deletion and preserve per-version scoped evidence. Keep capability
closed until all those pieces and their UI/isolation/recovery tests are delivered.

See `../sprint4/local-visual-plan.md`. This is media parsing isolation, not the
hardened learner-code execution boundary. It does not finish multimodal Alpha 2.

Primary references: [FFprobe/MOV input controls](https://ffmpeg.org/ffprobe-all.html),
[Tesseract local languages and CLI](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
