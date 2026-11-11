# Small native assignment-output review

Date: 2026-10-29. This is a bounded review of actual local model output for the
internal Sprint 5 workflow, not representative model evaluation or the independent
real-video/audiovisual quality gate. There is no corresponding recording for
these newly authored MIT-licensed subtitle fixtures in `samples/`.

## Expectations fixed before inference

Use the existing `qwen3:4b` only, with a freshly verified full digest and Ollama
engine pin. No weight download, provider fallback, owner-data changes, public
generation or default registry registration. Contexts require all external-topic/
document permissions explicitly false. Use a separate disposable PostgreSQL and
test-only processor registration; run the actual application graph, leased-call
receipts, checkpoint continuation and final evidence binding. Do not replace model
responses with authored replies. Run one workflow per case, stop on a terminal or
transient failure rather than repeating until success; first-pass maximum nine
physical calls (two supported cases at four calls each including one possible
revision, plus the single extraction for the insufficient case).

| Case | Explicit learner | Expected supported goals | Forbidden requirements | Expected result |
|---|---|---|---|---|
| `typed-list-en.vtt` | Intermediate experience; beginner difficulty; English; 45 minutes | Create a FastAPI GET route; return a string list with `response_model=list[str]` | Database/ORM, auth, deployment, pytest/TestClient, async functions, request-body validation | Reviewable small draft using only one or both supported goals and stable selected tutorial evidence; honest omissions |
| `health-route-tr.vtt` | Intermediate experience; beginner difficulty; Turkish; 30 minutes | Create a FastAPI application and GET route returning a constant dictionary | Database, login/auth, deployment, testing frameworks, async functions or complex validation | Turkish small draft with inspectable original citations; no full solution in hints |
| `insufficient-en.vtt` | Intermediate experience; beginner difficulty; English; 30 minutes | None: the text only describes an absent recording/title card | Any invented technical objective, route exercise or external prerequisite | Explicit insufficient coverage; safe failure before selection/generation and no draft |

Review actual extracted goals/quotes/coverage, selection and generated content:
semantic support versus literal quote membership, forbidden topics, clarity,
estimated effort versus explicit time, complete requirement/acceptance/rubric
relationships and progressive hints. Manual review does not execute learner code,
prove exact completion time or validate every possible solution. Record failures
and transient/provider issues separately from contract validity and native quality.

## Results

The first pass used the unchanged `caaa619` application profile. Both supported
cases timed out during extraction (42,061ms English; 42,057ms Turkish), each with
one failed `provider_timeout` receipt, nullable token counts and no draft. Their
run status was `retrying`; the probe stopped and deleted its test project rather
than automatically retrying. No native supported-draft quality claim is possible.

The insufficient case completed in 23,015ms and returned no goals, but referred
to nonexistent slice `s01000` instead of supplied `s00000`. Application validation
rejected it as `invalid_output` during extraction; no valid insufficient-coverage
checkpoint, selection or draft was accepted. This is not a successful abstention.
Three physical calls total; all test projects/contexts and in-memory artifacts
were removed. Exact output and interpretation will be recorded after inspection.

Predeclared follow-up diagnosis: one <=55-second streamed observation of the same
English extraction request (same model/digest/options/prompts/schema, only stream
delivery changed). Record first-content latency, content chunk/character counts,
completion/usage if available, and whether thinking appeared (never its content).
This is a diagnostic fourth call, not a retry accepted by the application or a
quality pass. Do not extend the production deadline based solely on two timeouts.

The diagnostic completed in 50,720ms, first content at 19,973ms: 652 input tokens,
391 output tokens, no thinking/tool calls. It would miss the unchanged 42-second
application socket deadline. It also had non-null reasons for `supported`
coverage and quotes with added quote/escape characters absent from the source;
therefore completing later would still not make this a valid extraction.

Predeclared single corrective pass: encode supported/insufficient status-specific
fields in the JSON schema, constrain slice IDs to the actual batch, and clarify
short literal quotes/local goal IDs in versioned extraction prompt/schema v2.
Keep deterministic quote/reference checks and all resource/deadline bounds.
Run each of the same three cases at most once again (<=9 physical calls total in
this pass), without retries on timeout. Record timing and validity honestly; this
does not authorize repeating until a draft succeeds or changing expected goals.

## Corrective pass and decision

The correction uses `tutorial-objectives-v2` / `tutorial-objectives-json-v2`:
status-discriminated coverage schemas, actual-batch slice enums in anchors and
coverage, explicit local goal IDs and short literal quote instructions. Strict
quote membership, coverage completeness, source identity and UTF-8 bounds remain.
The recipe/request hashes change; old pinned progress cannot silently adopt v2.
No transport, model, context/output budget, timeout, queue limit or lease changed.

| Case | Actual corrective result | Review |
|---|---|---|
| English typed list | Extraction timed out at 42,057ms; no accepted extraction/draft | Supported-draft quality remains unreviewed |
| Turkish health route | Extraction timed out at 42,058ms; no accepted extraction/draft | Supported-draft quality remains unreviewed |
| Insufficient title card | Structurally valid extraction in 34,803ms, selection in 12,307ms, generation timed out at 42,064ms | **Failed semantic abstention:** it made “no learning goals can be derived” into a `supported` goal, then selected it. No draft was published, but the accepted coverage is semantically wrong |

Exact public sample output, request/recipe fingerprints, timings, nullable token
usage and failed receipts are in [native-output-results.json](native-output-results.json).
The two passes plus the diagnostic made **nine actual inference requests** (3 +
5 + 1), below the predeclared maximums. No retries were made after a timeout.
Every test project/context and in-memory artifact was deleted after its run.
The data is authored/licensed demonstration content, not owner tutorials or media.

The review **does not pass**. Stronger decoding enforces structural invariants;
it does not verify semantic support, abstention, useful objectives or solvability.
The negative case is a failure, not a successful native-generation example. No
supported draft, effort estimate, language quality or progressive hint quality
was available for review. Keep the default registry and public producer closed.
No full Sprint 5 or Sprint 4/Alpha 2 quality approval is claimed.

Next is a bounded correction of the demonstrated local latency and false-positive
objective behavior. Use these recorded failures, preserve the lease/call fences,
declare any new profile/prompt budget before inference, and verify with a small
fixed positive/insufficient set. Do not raise deadlines blindly, weaken quote
checks, add a title-card keyword filter or repeat runs until a favorable result.
Per-document approval is now an owner-confirmed product decision; its capture/UI
implementation remains later in the existing Sprint 5 plan.

## Predeclared compact extraction pass — 2026-11-11

This follow-up tests extraction only, using the same two positive and one
insufficient MIT samples and the expectations above. It does not rerun full draft
generation or replace the failed end-to-end review. At most **three physical
inference requests**, one per sample, with no retry after timeout, invalid output
or semantic failure. Stop after extraction and inspect its actual goals, quotes
and complete coverage; do not select or generate an exercise in this pass.

Candidate `tutorial-objectives-v3` / `tutorial-objectives-json-v3` sends only the
explicit output language and each slice's local ID, origin label and lossless
text. Source/segment IDs, generations, processing versions and character offsets
stay authoritative application state, still pinned by the full context digest.
The shorter prompt defines goals as demonstrated technical actions and explicitly
separates absence/announcements/limitations from goals. Quote length is tightened
from 240 to 80 UTF-8 bytes in application validation, with a matching native
character ceiling; the stricter byte check remains necessary for multibyte text.
Two goals/two anchors, every-slice coverage and exact quote membership remain.

Keep the same installed `qwen3:4b`, freshly verified full digest and engine pin,
non-thinking JSON decoding, `keep_alive=0`, four inference threads, 16,384 context,
2,048 output tokens, 42-second inference/60-second call deadline and all existing
worker/lease/checkpoint limits. Do not download/build an image or weights, extend
deadlines, add a semantic judge or filter sample-specific words. The owner's
services are stopped; preserve them and mount existing weights read-only into a
disposable model container using the cached image. Use isolated PostgreSQL,
ordinary source/context processing and leased-call/checkpoint acceptance. Record
native timings, returned JSON, usage and strict/semantic failures separately.

Passing extraction here requires actual supported technical goals and valid
original quotes for both positive cases within the unchanged deadline, and empty
goals/explicit insufficient coverage for the negative case. A shorter malformed
answer or rejection of an overlong false-positive quote is not correct semantic
abstention. No result opens public generation or certifies supported draft quality,
solvability, overall Sprint 5 or the independent real-video review.

## Compact extraction results — 2026-11-11

Fresh inventory verified the same installed digest
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`
and Ollama 0.40.3. Exactly three physical calls were made, with no retries,
selection or generation. Actual JSON, request/recipe hashes, nullable usage,
receipts and cleanup are in
[native-extraction-v3-results.json](native-extraction-v3-results.json).

| Case | Actual extraction result | Manual review against the fixed expectations |
|---|---|---|
| English typed list | Structurally accepted in 37,599ms; 428 input / 261 output tokens | Literal quotes support creating the app instance and keeping the import/example in one file. Both expected core skills—GET route and typed string-list response—are omitted. This is not the expected assignment coverage |
| Turkish health route | `provider_timeout` at 42,042ms; no accepted extraction; token usage unknown | Supported-goal and Turkish-output quality remain unreviewed |
| Insufficient title card | Structurally accepted in 29,197ms; 298 input / 173 output tokens | Still **failed semantic abstention**: a description of absent instruction becomes a `supported` goal despite a valid short literal quote |

The compact input is 1,914/1,870/1,318 UTF-8 bytes versus
2,770/2,726/1,970 for the v2 messages reconstructed from the same authoritative
contexts. This is a serialization reduction, not a representative latency result
or quality improvement. The first bounded English success does not resolve the
Turkish deadline failure or the semantic failures. The negative goal's ID matching
its slice ID is legal under the contract; its meaning is the failure.

The extraction review **still does not pass**. No draft was attempted/published,
and the negative example was deliberately not advanced to selection; do not claim
it would have safely abstained later. The ordinary worker registry remains empty.
All test contexts/runs/artifacts and disposable schemas were removed. Existing
owner containers stayed stopped; image IDs and volume names were identical after
cleanup. Model weights were mounted read-only in a disposable cached-image
container, with an internal-only network and temporary loopback relays. No image
build/download, weight installation or owner-stack configuration change occurred.

Next take one bounded application-level step to reduce duplicated model output:
a compact extraction wire contract with goals emitted before coverage bookkeeping,
and application-owned goal identities/coverage reconstruction. Preserve explicit
insufficiency for every uncovered slice and all literal/source/recipe fences;
declare the mapping and fixed native pass before inference. This is a candidate
for the observed output/latency problem, not a claim it will solve semantic
abstention. Do not continue tweaking the same prompt or raising deadlines until a
favorable answer appears. Native quality remains required before generation is
enabled; approved document capture and draft activation remain planned Sprint 5 work.

## Predeclared compact wire pass — 2026-11-11

Profile `tutorial-objectives-v4` / `tutorial-objectives-json-v4` changes the model
response contract, not just prompt wording. The wire object is:

```json
{"goals":[{"description":"Define a GET route.","anchors":[{"slice_id":"s00000","quote":"literal source text"}]}],"insufficient":[{"slice_id":"s00001","reason":"No demonstrated technical action."}]}
```

The model emits no goal IDs, supported statuses or repeated coverage links.
`goals` precedes `insufficient` in the serialized schema (including sorted JSON).
The application assigns `goal0`, `goal1` in returned goal order. Every supplied
slice needs anchors or one unique explicit insufficiency entry; an omission,
foreign/duplicate insufficient ID, anchored/insufficient contradiction, repeated
anchor or identical goal row is invalid. One goal can anchor two slices, two goals
can share a slice, and multiple distinct anchors in a slice do not duplicate its
coverage ID. Empty goals require explicit insufficiency for every supplied slice.

Normalization `compact-extraction-map-v1` reconstructs the existing canonical
`BatchExtraction` checkpoint with batch-ordered coverage, original slice/quote
binding and application-owned identities. Replay checks those identities/order;
the recipe pins wire schema, canonical schema and normalization version. Old v3
responses/checkpoints are not auto-adapted. Bounds remain two goals/two anchors,
80-byte literal quotes and 180-byte descriptions/reasons. Interpretation remains
unreviewed; structural conversion cannot prove technical support or abstention.

Before inference, retain the same three MIT samples, expected core skills,
forbidden topics and explicit learner settings above. Perform **at most three
physical extraction calls**, one per sample, with no retries or selection/draft
generation. Inspect the actual compact response and normalized checkpoint; compare
raw/canonical output byte lengths as serialization evidence only. A timeout,
invalid response or incorrect goal ends that case; do not change the profile or
repeat until favorable output. Recheck the same existing model/digest/engine;
use unchanged provider decoding, 42/60-second deadlines and worker/lease limits.
Reuse cached images and read-only installed weights in a separate disposable
environment, preserving the owner's stopped stack and data. No download, image
build, semantic judge, keyword filter, default registry/public generation or
independent real-video approval is included.

## Compact wire results — 2026-11-11

Exactly three native calls used the unchanged installed digest/engine, decoding
and deadlines. No retry, selection or draft generation was attempted. Exact wire
JSON, receipt metadata and interpretation are in
[native-extraction-v4-results.json](native-extraction-v4-results.json).

| Case | Actual result | Review |
|---|---|---|
| English typed list | `provider_timeout` at 42,042ms; token usage unknown | No returned/accepted extraction; expected core skills cannot be reviewed |
| Turkish health route | Response in 40,509ms, 503 input / 204 output tokens; rejected `invalid_output` | Added quote characters are not literal source substrings. `s00000` is both anchored and insufficient, is repeated in insufficient, and `s00001` is missing. Uploaded text is incorrectly described as ASR/OCR. Import/app setup does not cover the expected GET/constant-dictionary behavior |
| Insufficient title card | Response in 24,118ms, 311 input / 143 output tokens; rejected `invalid_output` | A literal short quote still anchors a nontechnical absence-of-content meta-goal. The same slice is also insufficient. Safe contradiction rejection is **not successful semantic abstention** |

All cases retained only the initialization checkpoint: zero accepted extraction,
selection or generation and zero drafts. Successful TR/negative physical-call
receipts establish HTTP/JSON completion, not acceptance of the interpretation.
The converter rejected the native contradictions without repairing quotes,
dropping reasons or choosing whichever branch would allow publication.

The **native review still fails**. Authored protocol fixtures establish a smaller
wire representation than the equivalent normalized checkpoint. No native response
was valid enough to normalize, so no native wire/canonical size or latency gain
is claimed. Original source hashes, null unknown usage and the zero-spend receipts
are retained; all test data, schemas, queue keys, containers and network were
removed. Existing container/running state, image IDs and volume names stayed
identical; installed weights were read-only and no image/weight was built/downloaded.

This completes the bounded compact-wire software change, not native goal/draft
quality. Stop the prompt/profile retry sequence here. The next independent
implementation is the already planned Step 5 learner-approved official-document
capture; it must not enable generation or imply that these native failures are
resolved. Native latency, literal quote fidelity, core-skill extraction and
semantic abstention remain explicit gates before user-facing generation, with
full generated-draft review still required. No later sprint or new evaluator opens.
