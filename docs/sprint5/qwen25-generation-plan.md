# Separate local generation candidate: Qwen2.5 7B Instruct

Date: 2026-11-21. Status: **installed; full GPU placement verified; first native
extraction timed out; candidate closed**. The owner requested a
free local Ollama model that fits the available hardware, including a download if
needed. This authorizes the single contingency below after the installed
Qwen3.5 candidate stopped. It does not add automatic application downloads,
fallback, model rotation or a public model picker.

## Baseline and hardware decision

The installed Qwen3.5 4B candidate's first English extraction timed out at
42,044ms. The selected model was observed fully resident on the RTX 4060 Laptop
GPU, with 3,627,171,183 allocated VRAM bytes. No extraction or draft was accepted;
the other cases were not attempted. The native runtime remained healthy and idle
after `keep_alive=0`, with no observed out-of-memory failure. Preserve that failed
receipt and review in [the native review](native-output-review.md) and
[the Qwen3.5 plan](qwen35-generation-plan.md). A timeout without a returned
response leaves its semantic quality unreviewed; it is not proof of bad content
or a broken GPU. Do not retry that candidate or increase its deadline.

Select exactly **`qwen2.5:7b-instruct-q4_K_M`**, an approximately 4.7 GB official
Ollama tag with expected family **`qwen2`**. The host has an RTX 4060 Laptop with
8 GB VRAM, 16 GB system RAM and a working native Ollama service. Weight size and
the estimated additional context memory make this a plausible hardware fit, not
a guarantee of full GPU loading, peak memory, latency or quality. Verify actual
resources before and during its real request. Do not change driver, service
configuration, existing project `.env`, owner data or another model's lifecycle.

Download that one named public model through the existing Ollama service. Keep
the installed weights as the intentional owner-authorized result; never commit
them or copy Ollama credentials into test resources. Do not pull another model,
refresh previously installed tags, build/download a Docker image or use a paid or
remote inference service. An unavailable runtime or insufficient disk/VRAM is a
preflight block, not permission to remove owner files or select another model.

## Identity and software checks before inference

The mutable public tag and its short website hash are not an installed identity.
After download, freshly read local tags/show/version metadata and record the full
manifest digest, actual quantization, local completion capability and engine pin.
Fresh local metadata verified native engine **0.33.3**, exact tag and Q4_K_M
quantization, local completion capability and an idle model queue. Ollama completed
SHA verification; installed model size is **4,683,087,332 bytes**. Full manifest:
`845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`.
This pin was recorded before inference. No earlier model tag was refreshed.
Require family `qwen2`, the exact selected model name, and no remote model/host.

Extend only the explicit application-owned model/family compatibility boundary;
preserve the existing Qwen3 default and earlier identities. Keep before/after
identity checks, response-model checks, strict JSON/usage/size validation,
thinking/tool-output rejection and request budgets. The adapter must not pull,
discover, rotate or fall back to models. Verify supported and rejected identity
cases with authored HTTP fixtures before native inference.

Keep request hashes and checkpoint headers pinned to the exact selected
model/digest/engine. Verify that another model's accepted checkpoint cannot resume
under this identity, and that unchanged legacy Qwen3 requests retain their bytes
and hashes. Preserve the recipe, receipt, scope/lease/deletion fences, one physical
call per delivery and the empty default processor registry. Use explicit test-only
registration for the isolated review. No public endpoint or migration is added.

## Fixed inputs and bounded pass

Keep the existing evidence-unit profiles unchanged:
`tutorial-objectives-units-v1`, `tutorial-objectives-units-json-v1` and
`evidence-unit-extraction-map-v1`. All source text must fit one batch without
truncation. The application still derives whole literal quotes from selected
unit IDs and verifies complete coverage, original source/version/span bindings
and exact checkpoint replay. No quote repair, different partition, prompt tuning,
sample filter, semantic evaluator or weaker validation is included.

Use the same authored MIT samples, in this order, with the original expectations
in [the native review](native-output-review.md):

| Case | Explicit learner | Required coverage and result |
|---|---|---|
| `typed-list-en.vtt` | Intermediate experience; beginner difficulty; English; 45 minutes | Extract GET-route and typed string-list response skills, including `response_model=list[str]`; produce a reviewable small source-supported draft if the extraction gate passes |
| `health-route-tr.vtt` | Intermediate experience; beginner difficulty; Turkish; 30 minutes | Extract application/GET-route behavior returning a constant dictionary; produce a small Turkish source-supported draft if the extraction gate passes |
| `insufficient-en.vtt` | Intermediate experience; beginner difficulty; English; 30 minutes | Empty goals and explicit insufficient coverage; stop before selection/generation with no draft |

Preserve source SHA-256 values:

- English: `96c24a31d53276ac5993972fdcd71eda2ecc486de4af89941d55f9bffe07a0f7`.
- Turkish: `abcb58150b6e90eae5b6d9e5c8222c6c06dfc6b1d1713bca51d305d958be1c11`.
- Insufficient: `2edbb9dc4b742895946d424b57949c7dcb91b8413356bfeb9fa226bf69a8c2a7`.

Forbidden requirements remain databases/ORM, authentication, deployment, testing
frameworks, async functions and complex/request-body validation absent from these
sources. The negative case may not invent a technical objective, route exercise
or external prerequisite. Keep all three external-topic/document permissions
explicitly false. No official-document retrieval is included.

Use real application ingestion, saved contexts, leased model-call receipts and
graph checkpoints against separate disposable PostgreSQL data. Observe the exact
model/digest and allocated VRAM through the native runtime during the real call;
driver availability alone does not prove GPU use. Retain these request limits:

- `temperature=0`, four threads, `num_ctx=16384`, `num_predict=2048`;
- `stream=false`, `think=false`, `keep_alive=0`;
- 42-second inference and 60-second acceptance deadlines;
- unchanged worker, lease, context, request/output and checkpoint budgets.

This non-thinking model still passes through the existing thinking/tool-output
rejection. A requested flag, valid JSON or known unit ID is not a quality result.
Do not add a special response repair or relax protocol validation for this model.

Run at most **three extraction calls**, one per sample. Inspect each actual result
before the next. **The first timeout, invalid response or semantic failure ends
this candidate immediately**; mark all remaining cases not attempted. No retry,
diagnostic, longer deadline, expectation change or recreation of a failed run.

Only if all three extractions pass, continue the **same accepted positive
checkpoints** through selection and generation. At most the existing one
correction per positive case is permitted, and only when its actual checkpoint is
`revision_pending`: **nine physical calls maximum in the whole candidate**. A
terminal, transport or semantic failure stops continuation. Do not reextract or
rewrite accepted state to obtain a more favorable draft.

Record raw returned wire, full unit bindings and canonical coverage, source/
context/request/recipe/model pins, actual nullable token usage, zero paid spend,
elapsed time and model placement separately from manual semantic judgment. Review
actual supported requirements, requested language, effort, acceptance/rubric
relationships and progressive hints; no full solution should appear immediately.

## Cleanup and completion boundary

Confirm this review's model unloads after each request. Remove its disposable
projects, artifacts, contexts, runs, receipts, checkpoints, schemas and temporary
resources. Preserve installed weights and owner services/data. Compare original
container states, image IDs, volume names and runtime health; distinguish the
single intentional model download from disposable test cleanup.

This candidate ends at a recorded preflight block, its first native failure or
the fixed extraction-and-draft review result. The owner-authorized contingency is
finite: a failure starts no third model, prompt/profile tuning loop or larger
resource budget. Record the concrete remaining model/runtime decision before
another candidate. A successful small review permits only the already planned
conditional Sprint 5 producer/progress/UI/document-generation work. Public
generation stays closed until that work and its acceptance checks pass; no Sprint
6, full Sprint 5 completion or independent real-video/Alpha 2 approval follows.

## Recorded outcome

The exact installed identity above passed preflight on engine 0.33.3. The first
English extraction made exactly one physical call, timing out at **42,043ms**;
the failed receipt records **42,050ms**, unknown/null usage and zero paid spend.
Only initialization checkpoint 1 exists. No extraction or draft was accepted.
Turkish, insufficiency and all selection/generation cases were not attempted.
No retry, preload, diagnostic inference, longer deadline or third model followed.

The exact model/digest was observed with **5,465,282,968 bytes entirely in VRAM**
at context 16,384. Read-only runtime logs confirmed 29/29 layers offloaded to GPU
and partial prompt processing (512 tokens, 85% progress, 13.46 seconds). This is
partial timing evidence, not completed token usage or a successful response. The
model fits this GPU; its output quality and success within the current deadline
remain unreviewed. See [the raw result](native-qwen25-gpu-results.json).

Normal application deletion removed all disposable records/artifacts and the
private schema. The temporary PostgreSQL/Redis containers were removed; original
containers/states, images, volumes, networks, native service and existing model
digests were preserved. The downloaded weights intentionally remain installed.
Next prepare a concrete runtime/budget proposal using the existing observations
before another native run; do not reopen this failed candidate or silently raise
its budget. Public generation/default registration and later sprints stay closed.

## Primary references

The [official Ollama model tag](https://ollama.com/library/qwen2.5:7b-instruct-q4_K_M)
lists Q4_K_M, approximately 4.7 GB, family `qwen2` and Apache 2.0 licensing. The
[Qwen model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) describes the
instruction-tuned multilingual model and structured-output training; neither
source establishes this project's latency or semantic acceptance. Ollama documents
[NVIDIA support](https://docs.ollama.com/gpu),
[GPU-placement inspection](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu)
and [JSON-schema requests](https://docs.ollama.com/capabilities/structured-outputs).
Fresh installed metadata and the actual finite result remain authoritative.
