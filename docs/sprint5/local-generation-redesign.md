# Local assignment generation: evidence-unit selection

Date: 2026-11-21. Status: owner-selected direction; items 1–3 implemented and tested
(see `validation-record.md`). Remaining items below are planned. This is a different
extraction representation, not a successful native result or public generation enablement.

## Decision and evidence

The owner explicitly keeps **free, local automatic generation** in Sprint 5 rather
than narrowing the target to manual assignments. The delivered review/edit/activate
workspace remains available. The failed v4 review and its raw results remain in
[native-output-review.md](native-output-review.md); they are not superseded by a
software-only success or erased by this new plan.

The former model had to describe technical goals, copy exact quotes, refer to
source slices and account for insufficient slices in one answer. Actual outputs
missed core skills, fabricated a goal from absence of instruction, contradicted
coverage and added nonliteral quote characters. Both semantic and runtime failures
must still pass the original fixed expectations.

Change the extraction task to **select application-owned evidence units**. The
model supplies goal descriptions and unit IDs; the application derives quotations
from immutable source spans. This removes model-authored quote bytes, not the
need to judge whether a goal is actually taught. Shorter output might help latency;
unit labels can increase input size. Neither improvement is assumed before measurement.

Read-only feasibility checks found cached weights for the existing container
`qwen3:4b` path, but the currently running native Ollama has a different engine and
model inventory. It is not an interchangeable endpoint. Historical digest/engine
pins must be refreshed through the actual isolated runtime before inference.
Container GPU access is not currently configured. This plan requires no new model,
GPU/runtime installation, owner service restart, timeout increase or owner `.env`
change. Do not publish host paths, private inventory or owner content in results.

## Representation and invariants

Retain the existing ordered `SourceBatch` / `PromptSlice` plan: <=4 slices/batch,
<=1,800 UTF-8 bytes/slice, <=20 batches. Every character of every selected slice
remains present; an oversized context fails explicitly rather than selecting less
source material. Do not add sentence-quality heuristics or a title-card keyword filter.

Within each slice, greedily take complete Unicode characters until the next would
exceed **80 UTF-8 bytes**, then start the next unit. Preserve whitespace, punctuation,
normalization form and original order exactly. This is a byte partition, not sentence
or semantic segmentation; adjacent units can split a word/code expression. Empty,
NUL-containing, invalid-Unicode or incoherent source spans fail without returning a
partial plan. Nonempty whitespace units remain in the input; they cannot later be
accepted alone as a meaningful quote.

Give units batch-local sequential IDs (`u00000`, `u00001`, ...). Each immutable
unit retains its parent slice, source/segment identity, processing version, modality,
origin, absolute source-character start/end and exact text. Unit IDs are scoped to
one versioned batch plan; they are **not** new public citation IDs. Public citations
continue to use existing stable segment IDs, timestamps and processing generations.

Hash the partition version, ordered batch/slice identity and complete source spans.
The workflow recipe also pins this version, normalization version, wire/canonical
schemas and request identity; the context hash supplies tenant/project/context and
selected-generation binding. The pure planner does not authorize a caller or replace
`checked_context`, membership locks or authoritative evidence binding.

The new model wire retains <=2 goals, <=180 UTF-8 byte descriptions, and 1–2 unit
references per goal. It emits no `quote`, source UUID, timestamp, origin or offset.
Input groups `{id, origin, units: [{id, text}]}` under each parent slice. Send
each character once through those ordered units, without duplicating full slice
text or sending private source metadata for every unit. Source identities and
spans stay authoritative application state. Output has the following bounded shape;
IDs in this illustration are placeholders, not native output:

```json
{"goals":[{"description":"...","unit_ids":["u00000"]}],"insufficient":[{"slice_id":"s00001","reason":"..."}]}
```

For every parent slice not referenced by a goal, require the existing explicit
insufficiency reason. Reject missing/foreign/duplicate/contradictory entries rather
than repairing them. Resolve each selected ID to the **entire** original unit;
never take a convenient prefix, fix quote spelling or silently choose a branch.
All original literal, duplicate-anchor and complete-coverage checks remain.

Private accepted batches retain the strict model `selection`, `unit_plan_sha256`,
and ordered per-goal `unit_bindings` alongside normalized literal anchors. Bindings
contain the entire selected units, including identity, absolute spans and text;
equal quote bytes at another occurrence cannot silently replace a selected unit.
Replay rebuilds the plan from the same authoritative context and checks IDs,
spans, complete text and mapping. The initial batch-plan hash includes both
request and unit-plan digests; the recipe pins the private accepted-batch schema.
Old v4 checkpoints are
not converted or resumed with this recipe. Old saved drafts/activated versions stay
readable through their existing contracts. No new database table/migration is
needed for a versioned private checkpoint payload; any later schema change requires
its own migration and scope/deletion coverage.

## Ordered implementation

1. **Pure evidence-unit planner — implemented.**
   `curriculum/evidence_units.py` validates `SourceBatch` input and returns immutable
   unit spans with a deterministic plan fingerprint. Tests cover exact reconstruction,
   Unicode/byte edges, nonzero source offsets,
   strict bounds, mutated input, deterministic IDs and changed source/recipe identity.
   This first slice does not change `objectives.py` extraction, call a model, enable
   a registry or claim improved model behavior.
2. **Wire conversion and exact replay — implemented.**
   `objectives.py` uses strict unit-selection responses, per-batch ID enums and
   application-owned whole-unit quote normalization. Explicit insufficiency and
   canonical `BatchExtraction` goal/coverage order remain unchanged. Prompt/schema
   versions are `tutorial-objectives-units-v1` / `tutorial-objectives-units-json-v1`;
   mapping is `evidence-unit-extraction-map-v1`. `workflow.py` retains selections,
   complete bindings and plan digests and rechecks them before resuming; old v4
   wire/checkpoints are rejected. The graph structure/version stays unchanged;
   its changed recipe separates the new representation. The actual provider's
   pure `prepare` path checks input/schema/request bytes before inference or call
   receipts. ID/escaping overhead causes an earlier bounded batch flush or explicit
   failure, never lost source text or increased context/call budgets. All external
   flags, default registration and public generation remain closed.
3. **Workflow regression and review — passed.** Focused extraction/workflow and
   full backend unit tests pass, along with real PostgreSQL cancellation,
   membership, lease/call/checkpoint, publication and deletion regressions. Existing
   Celery process-loss tests also pass: after SIGKILL, a fresh worker resumes the
   accepted unit-selection checkpoint without repeating extraction; duplicate
   deliveries leave one draft/result. Authored HTTP replies remain labelled
   protocol fixtures. Celery/outbox, one physical call per delivery, original actor
   attribution, all-or-nothing publication and the empty default registry remain.
   Independent read-only review found no blocker. These checks claim no semantic
   or native success.
4. **One predeclared native pass.** Use the existing three MIT subtitle samples and
   their unchanged learner settings, core skills, forbidden topics and expected
   insufficiency. Verify the actual cached model digest/engine first; select no
   automatic fallback. Use an isolated cached-image runtime, read-only weights and
   disposable test data; if identity/resources are unavailable, record a preflight
   block instead of installing or changing the owner's running service. Keep the
   existing four threads, 16,384 context, 2,048 output cap, `keep_alive=0`, 42-second
   inference / 60-second acceptance and worker/lease limits.

   Make at most **three extraction calls**, one per sample, without automatic
   transient retry. Record raw wire output, literal mapping, complete coverage,
   nullable usage and elapsed time separately from semantic review. Both positive
   cases must teach the previously declared core skills; the title-card case must
   produce no goals and valid explicit insufficiency. A valid ID or application-made
   literal quote does not pass a semantically false goal. If any case fails, stop
   this candidate: no new profile, changed expectations, same-case retry, longer
   deadline, semantic judge or public generation.

   Only if all three extraction reviews pass, continue the **same accepted positive
   checkpoints** through goal selection and draft generation, with at most the
   already allowed one correction each. Total budget: **nine physical calls**
   (three extraction + up to six continuation calls). Review the actual drafts for
   supported requirements, language, feasible effort, criteria/rubric and progressive
   hints. No extra repair or extraction rerun after a failed draft.
5. **Existing remaining Sprint 5 scope, conditional on that evidence.** A passed
   tutorial-only draft review permits planning/enabling the existing scoped run
   producer and progress/cancel/retry UI, not broad automatic registration. Integrate
   the already approved per-document opt-in behavior before external-topic generation;
   saved permission alone never fetches a document. Use Steps 4–7 in the main plan
   for the remaining capture-binding/generation/acceptance gates. Confirm the full
   selected-source -> generated draft -> edit -> activate -> inspect/delete flow
   with real local outputs before claiming Sprint 5 complete.

## Stop boundary and next slice

Items 1–3 stop at the internal wire/checkpoint and software recovery boundary.
No native call, new provider/model, public run endpoint, runtime UI, submission, grader, tutor or
evaluator is part of those slices. Next `devam` verifies exact Git/CI, then begins
item 4's fresh isolated runtime identity preflight and finite native pass. Unit,
SQL adapter-restart and actual SIGKILL/replacement-worker checks already pass.
The old failed review remains visible. A failure in item 4
ends this finite candidate and returns the concrete model/runtime decision to the
owner; it does not start a prompt-tuning loop or automatically narrow Sprint 5.
The independent real-video/Alpha 2 review remains open.

## Protocol references

The existing local transport uses Ollama's [chat API](https://docs.ollama.com/api/chat)
and [structured JSON schema output](https://docs.ollama.com/capabilities/structured-outputs).
These document response format/runtime fields; they do not guarantee semantic truth,
latency or correct abstention for this project. Source-unit selection and its expected
benefit are application design hypotheses to test under the finite pass above.
