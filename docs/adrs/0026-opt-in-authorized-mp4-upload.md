# ADR 0026: Experimental standalone authorized MP4 upload

- Status: Accepted continuation of ADRs 0021–0025; disabled by default
- Date: 2026-10-27

Expose only the accepted local selected-frame/OCR path through an authenticated
multipart endpoint and same-origin server-only BFF/form. Use
`VIDEO_UPLOAD_ENABLED=false`, independently of the WAV gate, and a separate fixed
video capability endpoint. Configuration is not native readiness or accuracy.
Existing subtitle/chat/WAV limits, formats, providers and original TTL do not grow.

Accept one standalone MP4 <=100,000,000 bytes / 600 seconds, H.264/avc1 yuv420p,
<=1920x1080/60fps and zero-based/unrotated timeline. The credential-free native
service checks actual codec/timing; API/BFF never decode media. Uniform sampling
retains <=20 frames/literal OCR, not scene/vision descriptions. Explicit en/tr or
experimental en+tr, rights and permitted-derivative/temporary-original consent are
required. Ignore optional AAC; no audio transcription, player or playlist mapping.

Count actual wire bytes <=100,000,000+16,384 before multipart parsing; unfinished
reads time out after 30 seconds. Authenticate/gate before API reads, and enforce
same-origin/UUID/capability before BFF reads. Reject extra/duplicate fields and
malformed media; bound BFF marker count before allocating multipart objects.
One video delivery per API/BFF process bounds large-buffer concurrency and rejects
excess before reading, not a distributed/global quota. Increase only API tmpfs
from 64 to 256 MiB to fit a valid 100 MB spooled file; do not enlarge Server Actions.

Always register the existing atomic three-stage workflow, retaining its pinned
embedding target and full actor/project/tenant fences. Validate the scoped original
job receipt before returning only identifiers to the browser. Browser abort/timeout
does not cancel a job or guarantee rollback: preserve draft/key until confirmed
acceptance, and use source recovery controls for accepted work.

Project original-video lifecycle from scoped `video_inputs`/cleanup records, not
source metadata. Show expiry, retirement, pending/failed cleanup and independently
confirmed deletion separately. Poll cleanup after jobs finish and permit only
the original cleanup initiator to retry via the existing protected command.
Permitted selected frames/OCR survive original deletion until complete source/
project deletion. No migration is needed; existing records/keys already cover this
path. Public video reprocess remains closed. Existing `.env` and running services
are not modified during development verification. See the video-upload plan and
separately reported software/native/boundary validation.
