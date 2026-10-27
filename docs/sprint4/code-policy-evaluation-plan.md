# Paired frame-policy and authored code/terminal diagnostics

Date: 2026-10-27. Continue Sprint 4 measurement after the opt-in v2 producer.

## Scope and assumptions

Keep the uniform default, both immutable policies/profiles, upload flags, native
budgets and all application data/services unchanged. No model/provider/format,
schema, retention or public endpoint. This is an operator-only paired measurement
and a small authored reproducible probe set, not representative quality approval.

Compare the exact same authorized MP4/independent reference with uniform v1 and
change v2 under the same engine/language-data/language identity. Validate all
bindings, manifests and pixels. Preflight the combined edit-work budget before
scoring either result. Record gained/lost/shared/missed interval ordinals and each
policy's complete existing coverage/OCR diagnostics, including bad measurements.
Never rank policies solely by differently weighted all-frame OCR aggregates.
Separately aggregate OCR on identical images at shared actual PTS, rejecting
pixel conflicts instead of quietly discarding them. No automatic winner/default
promotion; null denominators and zero shared samples remain honest.

Add an explicit authorized stdin/reference CLI using the existing isolated tools.
Check input bytes before native work and expected metadata after the first result;
print only fingerprints/profiles/times/counts, not text, identifiers, pixels or
paths. No result exporter or app credentials. Native calls retain existing bounds.

Add five fixed independently authored terminal/code probes: a transient terminal
error with return, a one-digit code edit, cursor-only motion, a sub-second view and
Turkish/technical identifiers. Ground truth derives from the authored schedule,
never OCR. Use fixed text files with drawtext expansion disabled, fixed fonts and
codec/FPS, bounded temporary output and no networking. Preserve negative cases;
do not tune the sampling/OCR parameters to make this tiny set pass a quality gate.
Measure all cases or one explicit named case; valid poor measurements exit zero.

## Verification

Test paired profile/input binding, budget preflight, coverage gains/losses, common-
PTS image/metric arithmetic, null/missing/blank states, nested mutation and safe
CLI failures/ordering. Test authored schedules, complete labels/identifiers,
fixed rendering arguments and cleanup. Run actual isolated FFmpeg/Tesseract probes
and retain counts/errors separately from unit fixtures and hosted CI. Verify the
legacy evaluator output/native HTTP remains unchanged and run full regression.
No claim of real-IDE coverage, compiler correctness, scene recall or Alpha 2.
