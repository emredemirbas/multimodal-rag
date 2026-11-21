# Separate local generation candidate: installed Qwen3.5 4B

Date: 2026-11-21. Status: provider compatibility and replay implemented; the native
GPU candidate **failed at its first extraction with a timeout**. See
[the exact result](native-qwen35-gpu-results.json). The owner selected this
separate candidate after the finite Qwen3 evidence-unit failure, then explicitly
requested a hardware-compatible local Ollama model, authorizing a download if
needed and continued development. This supersedes the earlier planning-only and
no-download restriction for that bounded operator action. It adds no automatic
application download, model rotation or public fallback.

## Hardware and runtime decision

Fresh local inspection found an RTX 4060 Laptop with 8 GB VRAM, a working NVIDIA
driver, 16 GB system RAM and an idle native Ollama service. The existing pinned
Qwen3.5 model occupies about 3.4 GB on disk. It is the first candidate; no new
download is needed to test it. The earlier CPU-only container result does not
measure this native GPU path. Actual GPU loading must be observed during inference,
not inferred from driver availability or weight size.

Use the existing idle native engine **0.33.3**, explicitly pinned with the installed
model digest below, without restarting/reconfiguring the service. This is a
deliberate hardware/runtime selection under the latest owner request, not a claim
that native and container runtimes are equivalent. Keep application request,
context/output, thread and deadline limits unchanged. The prior six-GiB CPU
container cap is not a native-service setting; do not modify the owner's service
limits. Observe native VRAM/host-memory use within the available hardware and
retain `keep_alive=0` so this review's model unloads after each request. Use only
authored public MIT text and a disposable test PostgreSQL; prompts receive no
owner content or credentials. Provider requests remain bounded local-only calls
without tools, arbitrary URL retrieval or cloud model fallback.

If this finite candidate fails, the latest owner request authorizes one hardware-
fitting download if needed. The researched contingency is
`qwen2.5:7b-instruct-q4_K_M` (about 4.7 GB weights); do not download it preemptively
or run an unbounded model search. Any such separate candidate must be pinned and
declared before inference, with the same semantic/deadline gates. A runtime/GPU
failure must be diagnosed as such; a larger model is not its automatic remedy.

## Baseline and fixed decision

The previous candidate's first English extraction returned contradictory and
incomplete slice coverage. One physical call, no accepted extraction or draft;
the remaining samples were not attempted. Preserve its raw output and review in
[native-evidence-units-results.json](native-evidence-units-results.json) and
[native-output-review.md](native-output-review.md). Do not repair that response,
retry the old candidate or relabel the source as truncated: every source character
was present in the intentional byte-unit partition.

Read-only metadata from the existing native Ollama service identified:

- Exact model: `qwen3.5:4b`.
- Installed manifest digest:
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.
- Reported family `qwen35`, GGUF/Q4_K_M, local completion capability, no remote
  model/host. Vision/tools/thinking capabilities grant no use of those features.
- Native service engine `0.33.3`. This is metadata, not a tested inference path.

Do not pull the mutable public tag or assume the native service is interchangeable
with the cached isolated Ollama `0.40.3` runtime. The installed digest is the
candidate; public model listings or advertised benchmarks do not establish local
quality, latency, non-thinking behavior or compatibility.

Keep the current evidence-unit extraction prompt/schema/mapping, source material
and semantic expectations. Select the model/runtime explicitly. No paid API,
GPU/driver installation, owner-service restart/configuration change, arbitrary
model picker, automatic fallback or public registration is included.

## Ordered implementation

1. **Explicit provider compatibility, without inference.** Extend the application-
   owned identity allowlist to exactly `qwen3:4b` and `qwen3.5:4b`; preserve the
   existing Qwen3 default. Bind model names to fixed expected families (`qwen3`
   and `qwen35`). Require a full installed digest and actual isolated engine pin,
   completion capability and no remote model/host before and after every call.
   Retain exact response identity, JSON/usage/size/deadline checks, and rejection
   of thinking/tool output. Add no download, discovery or fallback in the adapter.

   Test both allowed identities/families, unsupported names, raw malformed values,
   wrong family/digest/engine, missing capability, remote metadata and response
   identity drift with authored HTTP protocol fixtures. These prove adapter
   behavior, not Qwen3.5 native quality. No public endpoint or migration is needed.

2. **Replay and software regression, without inference.** Verify legacy Qwen3
   request bytes/hashes and the current recipe remain identical when transport,
   prompts and normalization are unchanged. The checkpoint header already pins
   full model identity, and request hashes include the selected model. Reject a
   model/digest/engine change before resuming another identity's accepted state;
   never convert an old native result into the new candidate's extraction.
   Run focused provider/workflow tests and proportional PostgreSQL/worker recovery
   regressions with an explicitly supplied test registry. Keep one physical call
   per delivery, receipts, scope/lease/deletion fences and the empty default registry.

3. **Selected native GPU runtime preflight, then one finite pass.** Freshly verify
   actual tags/show/version pins, local family/completion capability, no remote
   model/host, an idle model queue and available VRAM/RAM. Do not copy credentials
   or publish host paths. The selected native `0.33.3` runtime replaces the former
   cached CPU-container proposal above; it is not assumed interchangeable.
   Observe `/api/ps` model/digest and allocated VRAM during the real request, and
   check this review's model unloads afterward. If identity/runtime/resources are
   unavailable, record a preflight block rather than downloading/restarting or
   changing service/driver settings. Download permission alone is not a remedy
   for unavailable runtime resources.

   After software checks and preflight, predeclare and run the same three MIT
   samples in order: English typed list, Turkish health route, insufficient title
   card. Keep their exact hashes, learner preferences, expected core skills and
   forbidden topics from [the original review](native-output-review.md).
   Each complete context must fit one batch without lost source text. Use real
   ingestion, saved contexts, leased receipts and graph checkpoints in a separate
   disposable PostgreSQL. The latest owner instruction authorizes implementing
   and exercising this finite candidate after its software checks pass.

   Keep `temperature=0`, four threads, 16,384 context, 2,048 output tokens,
   `stream=false`, `think=false`, `keep_alive=0`, 42-second inference / 60-second
   acceptance and existing worker/lease budgets. Requesting `think=false` is not
   proof of its behavior: any returned thinking/tool output still fails existing
   validation. Do not weaken that check or add another protocol/profile.

   At most **three extraction calls**, one per sample, with manual inspection
   before the next. **The first timeout, invalid response or semantic failure
   ends this candidate immediately**; mark remaining cases not attempted. No
   transient retry, diagnostic, prompt adjustment, sentence filter, longer deadline
   or expectation change. Only if all three extractions pass, continue the same
   accepted positive checkpoints through selection/generation and at most the
   existing one correction each: **nine total physical calls maximum**. An actual
   `revision_pending` checkpoint permits only that one declared correction; a
   terminal, transport or semantic failure ends the candidate. Never retry a
   failed delivery or recreate/reextract to get a better draft.

   Record raw wire, whole-unit provenance/mapping, coverage, request/recipe/model
   pins, actual nullable usage and elapsed time separately from semantic judgment.
   Review supported requirements, language, effort, criteria/rubric relationships
   and progressive hints in actual drafts. Clean all disposable data/resources and
   compare original container states, image IDs and volumes afterward.

## Completion and next step

This candidate ends with either an explicit preflight block, the first recorded
native failure, or the fixed extraction-and-draft review result. A failed result
returns a concrete model/runtime decision to the owner; it does not start another
candidate. A passed small review permits only the existing conditional producer/
progress/UI/document-generation work in the Sprint 5 plan. It does not complete
Sprint 5, open submissions/grading or close the independent real-video/Alpha 2 gate.

Items 1–2 pass software regression. Item 3 made exactly one native English call,
timing out at 42,044ms. Actual model/digest observations showed all 3,627,171,183
runtime bytes in VRAM with the unchanged 16,384 context. No extraction or draft
was accepted; Turkish/negative cases were not attempted, so their semantics and
all draft quality remain unreviewed. The runtime returned to idle without service
changes. This candidate is closed; no retry or larger deadline follows.

The owner's conditional download instruction now applies to the single researched
[Qwen2.5 contingency](qwen25-generation-plan.md). It is a separate explicitly
selected candidate, not automatic fallback within a run. Its download completed
and its first native extraction also timed out despite full GPU placement; that
candidate is now closed too. The installed weights are retained. See its recorded
result and runtime/budget continuation; preserve this independent failed result
and keep public generation closed.

## Protocol references

Ollama documents JSON-schema requests through the `format` parameter in
[Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).
Its [thinking controls](https://docs.ollama.com/capabilities/thinking) depend on
model/runtime behavior; requesting no thinking is not a quality or compatibility
guarantee. These references describe protocol options, not this candidate's native
success. The installed local manifest, not the mutable public tag, supplies its pin.
Hardware support and GPU-placement inspection follow Ollama's
[hardware documentation](https://docs.ollama.com/gpu) and
[local FAQ](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu).
The contingency weight size comes from the
[official Qwen2.5 tag](https://ollama.com/library/qwen2.5:7b-instruct-q4_K_M);
weight size alone is not a runtime-memory or quality guarantee.
