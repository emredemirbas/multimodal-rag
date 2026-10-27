# Local OCR and retained-PTS diagnostics: verification

Date: 2026-10-27. Scope: explicit stateless operator diagnostics within the
existing authorized MP4 limits; not scene detection or a representative benchmark.
Hosted CI is checked separately after push.

## Delivered boundary

- Strict operator reference/result JSON with exact input digest/bytes and expected
  video metadata; declared label status and up to 20 ordered disjoint intervals.
- Retained **actual PTS** interval coverage, all-sampled-frame normalized WER/CER,
  NFC-only case-sensitive literal CER, delimited identifiers and blank-view OCR.
  Never choose the best result; missing intervals remain separate from scores.
  Null denominators, insertions and rates above one remain visible.
- Whole-diagnostic edit-work preflight and existing bounded PNG/profile/timeline
  validation, including revalidation of mutable nested models. No label/text/
  identifier/pixel/path export in reports or raw exceptions on processing failure.
- Offline CLI plus mutually exclusive native `--reference`. Native byte/digest
  checks precede decoding; expected metadata is checked after extraction. No
  application API/project/storage/queue, migration, dependency change, provider,
  retention expansion, paid fallback or upload-default change.
- Pure normalization/identifier/edit-distance functions are moved unchanged from
  the ASR evaluator into a shared stdlib module. Existing ASR report semantics and
  imports remain compatible; the native visual image contains no ASR model or
  trusted database/worker modules.

## Software evidence

Focused OCR plus ASR diagnostics: **97 passed** (49 new visual cases and 48 existing
ASR cases, 0.69s). This includes arithmetic/rates above one, all-frame aggregation,
case/slash differences hidden by prose normalization but preserved literally,
Turkish/NFC/line breaks, punctuation-only labels, blank insertions, actual-PTS
half-open boundaries, gaps/all-missing labels, incompatible requested language,
strict interval/input/PNG/profile contracts, mutated models, bounded JSON/work,
safe CLI/fingerprints, pre-inference input binding and one controlled provider call.
The existing ASR exhaustive small distance-oracle test still covers the shared
distance implementation; no arithmetic algorithm or normalization version changes.

The committed JSON-only synthetic fixture was also executed through the offline
CLI: coverage **2/3**, identifier recall **0**, one unexpected blank-view OCR,
aggregate WER **1/3**, normalized CER **10/18**, literal CER **15/19**. It has no
corresponding native recording and keeps `declared-reference-result` binding.

An initial full run passed **718** tests but timed out in the pre-existing real
gallery worker post-PUT crash/replacement test (30-second completion deadline).
That exact test then passed independently in **3.12s** on fresh services. No
assertion/deadline/worker implementation was changed or test skipped. The root
cause of this first timeout is not established; retain it as intermittent evidence,
not an invented fixed diagnosis. A final full-suite repeat is recorded below.

Final full regression: **719 passed, zero skipped, 176.90s**, including all actual
worker SIGKILL/recovery/MinIO probes with `TEST_REAL_WORKER=1`. Both full runs and
the isolated repeat used fresh PostgreSQL/pgvector, Redis and MinIO containers,
random loopback ports, test-only allowlisted credentials and disposable tmpfs data.
No application `.env`, data volumes/schema/bucket/queue were used. Each teardown
removed only newly recorded container IDs. The existing upstream Starlette/httpx
TestClient deprecation warning remains unsuppressed. `git diff --check` passes.

## Actual native diagnostics

Built a separately tagged minimal visual image; exercised its updated authored
self-test and unchanged real private HTTP/native/profile-pinning probe in fresh
network-none/read-only/non-root/resource-bounded containers. No app credentials,
data mounts, published ports or model volumes. Inherited kernel/child socket
denial remains active. The private HTTP probe creates zero application records.

The unchanged authored 20-second English/Turkish card MP4 is **329,836 bytes**,
SHA-256 `683607d7a2985bf98fca722d0cc96117301d39cdbfaaf9f99862cf2814c2bbac`.
Literal labels are fixed in source, independently of recognized output. All modes
retain actual PTS **0 / 10,000 ms**, two of four candidates, covering both labels:

| Requested OCR | Interval coverage | WER | Normalized CER | Literal CER |
|---|---:|---:|---:|---:|
| `en` | 1 | 0.5 | 0.074074 | 0.074074 |
| `tr` | 1 | 0 | 0 | 0 |
| `en+tr` | 1 | 0.5 | 0.074074 | 0.074074 |

The existing `combined_language_turkish_exact` diagnostic remains **false**.
Explicit `tr` success on these artificial cards does not resolve mixed-language,
technical code/terminal/scene or representative quality. No identifiers or blank
views are labeled in this native fixture; do not claim native identifier/blank
quality from the software tests. `quality_approval` remains `not_established`.

The real native `--reference` CLI additionally passed with a host synthetic
reference mounted **read-only** into a new network-none tool, and fixture MP4
bytes piped from another isolated generator. It reports `verified-mp4-bytes`, both
intervals covered and the same `tr` zero errors without text/pixel export. It
creates no application row/object and does not delete a host input. Temporary
native contexts/containers are removed; the small synthetic reference is only a
temporary operator verification artifact, not private user media.

The ASR image separately builds and, without network/weights/application mounts,
imports its smoke/evaluator and verifies the shared Turkish normalization and
edit arithmetic. This checks packaging, **not a new native ASR quality result**.
CI's existing native visual self-test now executes the diagnostic/reference path;
all other backend/frontend/audit/image/workflow gates remain enabled.

## Limits and safety

Coverage is temporal retained-frame coverage, not semantic scene recall or verified
pixel/label correspondence. Exact deduplication may omit a repeated later view.
Missing intervals cannot be erased by good OCR; scored-sample rates exclude them.
No quality threshold, model/sampling change, vision description, transcript/frame
alignment or full Sprint 4/Alpha 2 approval. Real reference/results stay outside
the checkout and fingerprints should not be published for private clips.

The user's actual `.env` remains ignored/mode 0600, without changes; existing
application data, services and migration state are untouched. Frontend code and
dependencies are unchanged; no new local UI-test result is claimed for this slice.
