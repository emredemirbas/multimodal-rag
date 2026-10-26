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

The next stateless component adds an optional credential-free private HTTP listener
on an internal-only network, binding before inherited socket denial and verifying
a fresh child's restriction before readiness. Current API/workers are not attached.
Require explicit pinned processing identity and actual input digest on extraction;
validate bounded PNG/OCR/timelines on both sides. Limit connections, work, request
reading, native processing and response bytes/time; prohibit proxy/redirect/retry
or fallback in the client. It adds no project records, storage or upload capability.
The original CLI remains available. See `../sprint4/visual-service-plan.md`.

The following checkpoint component adds migration 0013 private scoped runs and
bounded PNG/OCR rows under the existing live actor/job/source/generation fence.
Pin actual input bytes/rights/profile before inference; atomically save/revalidate
one complete result with hashes and accepted counts. Membership remains locked
through commit and processing eligibility ends one hour after job creation,
without retry extension. PostgreSQL staging avoids premature untracked object
PUTs; complete source/project deletion cascades all bytes/text. No result enters
published evidence/usage. Retrieval after lease recovery is supported, but a lost
in-flight full extraction may repeat; per-frame decoding is not claimed. Exclude
this trusted DB code from the minimal native image. Registration/queue execution,
raw cleanup, final object adoption and UI remain follow-up. See
`../sprint4/visual-checkpoints-plan.md`.

Primary references: [FFprobe/MOV input controls](https://ffmpeg.org/ffprobe-all.html),
[Tesseract local languages and CLI](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
