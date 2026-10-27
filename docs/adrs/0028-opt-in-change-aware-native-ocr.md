# ADR 0028: opt-in change-aware native OCR

Date: 2026-10-27
Status: Accepted as an experimental fixed local policy, not a quality release.

Connect ADR 0027's v2 contract to actual isolated native OCR. Keep
`VISUAL_SELECTION=uniform` as the trusted worker default; `change` is explicit.
Pin selection with engine/language at first checkpoint initialization. Existing
pins win over configuration drift on incomplete/saved retry. No silent fallback,
old-generation conversion, public upload parameter or schema change.

The credential-free private listener supports only fixed language/selection query
values. Unknown, duplicate and additional parameters fail before native work. No
app identity/secret, arbitrary expression, URL or filesystem path crosses it. Both
policies share existing capacity, framing/deadlines and kernel/native restrictions.

Reuse bounded thumbnail scanning/ranking, retain the complete manifest, then decode
selected large frames in one second pass. A fixed expression matches rounded
millisecond source PTS, rather than seeking at a rounded target and substituting
a later frame. Require exact manifest/frame PTS, filenames/counts, geometry, PNG
and literal OCR integrity; any mismatch fails the whole call. Temporal pixel
returns remain distinct. Native CPU/wall/file/PID/tmpfs/network budgets do not grow.

The pinned official FFmpeg [select source](https://github.com/FFmpeg/FFmpeg/blob/n5.1.9/libavfilter/f_select.c#L303-L337)
defines source seconds; its [evaluator](https://github.com/FFmpeg/FFmpeg/blob/n5.1.9/libavutil/eval.c#L186-L189)
provides rounding. Exact output validation, not floating-point assumptions alone,
is the acceptance gate. Tests verify encoded fractional FPS as well as PTS.

The operator CLI adds `--selection change`; managed processing uses existing
checkpoint/gallery/index/citation/usage/deletion paths. Logs contain fixed policy/
counts, not scan hashes, pixels, OCR or filenames. Upload consent/retention stays
unchanged; the form does not promise a selection before a job is pinned.

One-second low-resolution differences are not semantic scene understanding.
Short/small edits can be missed; irrelevant motion can consume the budget; complex
clips can exceed unchanged limits. No descriptions, verified audiovisual alignment
or representative quality approval. See the `../sprint4/change-ocr-*` documents.
