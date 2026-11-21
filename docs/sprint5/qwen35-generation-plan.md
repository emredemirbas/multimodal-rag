# Separate local generation candidate: installed Qwen3.5 4B

Date: 2026-11-21. Status: **owner-selected plan only**. No provider change or
Qwen3.5 inference has been made. The owner explicitly selected this separate plan
after the finite Qwen3 evidence-unit candidate failed. This is not an automatic
fallback or a successful native result.

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
and semantic expectations. Only the explicitly pinned model changes. No model
download, paid API, GPU setup, owner-service restart/configuration change,
arbitrary model picker, automatic fallback or public registration is included.

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

3. **Isolated runtime preflight, then one finite native pass.** Locate the already
   installed manifest and referenced blobs without copying owner credentials or
   publishing host paths. Mount those weights read-only in the existing cached
   Ollama `0.40.3` image on a disposable internal network. Freshly verify its actual
   tags/show/version identity and local family/capabilities; the native `0.33.3`
   metadata above does not prove that runtime can load the model. Reuse the prior
   six-GiB model-memory limit and available host resources; no resource/deadline
   increase to evade failure. If weights/runtime/resources are unavailable, record
   a preflight block and stop before inference. Do not install, pull, restart the
   owner's service or silently use its endpoint instead.

   After software checks and preflight, predeclare and run the same three MIT
   samples in order: English typed list, Turkish health route, insufficient title
   card. Keep their exact hashes, learner preferences, expected core skills and
   forbidden topics from [the original review](native-output-review.md).
   Each complete context must fit one batch without lost source text. Use real
   ingestion, saved contexts, leased receipts and graph checkpoints in a separate
   disposable PostgreSQL. This plan's approval itself starts no inference.

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

Next `devam`: verify exact Git/CI, implement item 1 and its focused tests, then
continue item 2 as appropriate. Keep public generation closed. This planning
turn makes no Qwen3.5 inference and does not change the current provider.

## Protocol references

Ollama documents JSON-schema requests through the `format` parameter in
[Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).
Its [thinking controls](https://docs.ollama.com/capabilities/thinking) depend on
model/runtime behavior; requesting no thinking is not a quality or compatibility
guarantee. These references describe protocol options, not this candidate's native
success. The installed local manifest, not the mutable public tag, supplies its pin.
