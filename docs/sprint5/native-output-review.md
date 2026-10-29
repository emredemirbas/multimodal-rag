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
