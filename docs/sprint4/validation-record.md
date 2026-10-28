# Sprint 4 ordered-transcript playlist validation

Date: 2026-10-11
Status: Local playlist slice validated; not full multimodal/Alpha 2 approval.
The dependency-audit blocker is now resolved locally; hosted CI still requires a
push. The free local portfolio decision is recorded in ADR 0015.

## Delivered scope

- Additive migration `0005_ordered_playlists.sql`, ordered metadata snapshots and
  current successful snapshot references under tenant/project scope.
- Stable provider item/video identities, correct repeated-video relationships,
  explicit truncation and upload-link preservation across metadata reordering.
- Atomic authorized subtitle upload association; unchanged-key replay and conflict
  checks include the chosen video. Replacements preserve independent old sources.
- Per-playlist active lease cap, no-attempt capacity waiting, durable redelivery,
  independent cancellation/retry and a bounded operational waiting gauge.
- Accessible ordered videos, missing/ready/failed states, upload selector,
  truncation warning and accurate playlist-versus-transcript deletion wording.
- Source/project deletion and old citation stability retained.

## Checks

- Full backend suite with PostgreSQL, Redis, MinIO and `TEST_REAL_WORKER=1`:
  **90 passed, no skips** (37.20 seconds).
- Three actual test-owned Celery processes competing for two playlist slots:
  ten synthetic videos, observed maximum two running jobs and capacity waiting;
  nine successful subtitles and one malformed failure; only the failed video's
  corrected replacement processed, leaving the other nine attempts unchanged.
- Existing actual worker-death recovery, duplicate delivery and MinIO checks pass.
- Negative tenant/project upload, item reads and worker-claim tests pass; scoped
  foreign keys, concurrent replay, failed metadata refresh, stale snapshot item,
  repeated-video identity and project deletion are covered.
- Frontend **12 files, 37 tests passed**, lint and typecheck passed. Includes
  playlist selection, ordering, partial failure, deletion wording, malformed
  contracts and truncation surviving the server-only proxy's normalization.
- Production Docker builds pass, including the final frontend correction.
  Migration executes and repeats successfully; seven runtime services are healthy.
- Live Sprint 1/2/3 smoke regressions passed against the new stack.
- Final frontend rerun passed all 37 tests, lint and typecheck; Compose config and
  `git diff --check` passed. The ignored `.env` was not changed.

## Browser evidence

A test-owned project was seeded with clearly labelled synthetic metadata; its
outbox entry was removed in the same transaction before dispatch. No YouTube
request or provider key was used. Two synthetic subtitles were uploaded through
the API and processed by the normal Compose worker: one ready, one malformed;
a third item remained without a subtitle.

The production browser showed ordered 1/2/3 entries, **1 of 3 indexed**, **1 failed**,
an actionable partial-failure message and individual retry controls. The explicit
truncation warning survived source refresh. Selecting a video preserved its label;
inspection found that selection could enable the upload button without a file.
The button now also requires a selected file, with a regression assertion.
The final production rebuild was checked again: selecting the third video kept
the file-less upload button disabled, and the truncation warning stayed visible
after source refresh. No warnings/errors were observed in these browser flows.
The exact owned test project and its two uploaded files were permanently removed
after verification; durable artifact cleanup completed and project reads returned
404. Existing user data and shared volumes were preserved. This validates a
synthetic local fixture, not live YouTube availability or subtitle/video alignment.

## Dependency advisory and release gate

Initial full `npm audit` reported seven high findings. Regenerating the lockfile
with compatible published fixes updates `sharp` **0.35.4 → 0.35.5** and
`source-map-js` **1.2.1 → 1.2.2**. Production-only audit reports zero findings.
References: [sharp maintainer advisory](https://github.com/lovell/sharp/security/advisories/GHSA-wq5f-xc86-pv6w),
[source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

Initially `npm audit --audit-level=high` exited 1 with five high dependency-chain
findings, all originating in `braces@3.0.3` through Next's development ESLint plugin,
`fast-glob` and `micromatch`. The
[reviewed advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) lists no
patched version; the official npm registry still lists 3.0.3 as latest. Even the
current Next ESLint plugin 16.4.0 retains that dependency. The application's uploaded
transcripts never become lint glob patterns; this is an exposure observation,
not permission to waive the advisory or a claim of exploit immunity.

The follow-up replaces only the pinned Next lint plugin's root-directory lookup
dependency with a private, tested compatibility package backed by official
`tinyglobby@0.2.17`. Literal/absolute paths and glob/array roots are verified using
the real upstream helper; unsupported options and pathological patterns fail
closed. Next Core Web Vitals, TypeScript and accessibility violations still
produce their original diagnostics. Native imports in the CJS adapter receive
only a narrow file-specific style allowance; framework/accessibility rules are
unchanged. Braces/micromatch code is absent from the install/lockfile, not relabelled.

Clean `npm ci`, **5 lint compatibility tests**, full
`npm audit --audit-level=high` (**zero findings**), lint and typecheck pass.
CI retains the full audit and adds compatibility tests. No finding is suppressed,
no Next 14 downgrade or third-party fork is used. Docker copies the private
tooling package before clean dependency installation. See
`lint-compatibility-plan.md`. Changes remain uncommitted/unpushed; no hosted CI
success is claimed.

## Reproduce

```bash
docker compose up --build -d --wait --wait-timeout 120
set -a
source .env
set +a
TEST_REAL_WORKER=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend --tb=short
backend/.venv/bin/python scripts/smoke_sprint1.py
backend/.venv/bin/python scripts/smoke_sprint2.py
backend/.venv/bin/python scripts/smoke_sprint3.py
cd frontend
npm ci
npm test
npm run lint
npm run typecheck
npm audit --omit=dev --audit-level=high
npm run test:lint-compat
npm audit --audit-level=high
```

The real-process probe uses its own schema, Redis key prefix, queue, processes and
S3 prefix. Only its exact namespace/processes are cleaned; shared Redis, user data,
Compose workers and volumes are preserved.

## Remaining scope

The owner's subsequent free-portfolio direction and completed optional local
answer slice are recorded in ADR 0015 and
`../sprint3/local-model-validation.md` (115 backend, 40 UI and 5 lint-compatibility
tests, plus actual local model smoke). Managed providers are no longer a blocking
choice for this target. Local semantic embeddings and media remain separate work.

Official metadata imports still require an owner-configured server-side
`YOUTUBE_API_KEY`; no live provider request was verified. Managed LLM/ASR/vision,
retention/region/spend policy, binary input limits, FFmpeg isolation, meaningful
frame selection/OCR/alignment, visual citations and reviewed benchmarks remain
open. No arbitrary download, learned semantic model, external docs, assignment
or grading feature is added. See ADR 0014 and the open decision log.

## Subsequent local WAV upload slice (2026-10-23)

The initial playlist record above is historical, not the current complete feature
inventory. ADRs 0018–0020 and `audio-upload-validation.md` now record restricted
local WAV validation/inference, private resumable media jobs, versioned unreviewed
provenance, original retirement/cleanup and the experimental authenticated upload
API/BFF/form. WAV remains off by default with explicit weight/worker setup and
operator opt-in. The new slice passes 268 backend and 98 frontend tests plus a
separate native authored-speech BFF/queue/index/SSR/cleanup probe in a disposable
stack. These are not broad speech-quality, vision/OCR, assignment/grading or full
multimodal exit-criterion approval. Retain the previous failed vocabulary probe.

## Read-only local setup polish (2026-10-28)

`scripts/check_local_setup.py` diagnoses the base Compose prerequisites without
starting/stopping services, pulling images/models, changing files/permissions or
inspecting application data. It uses only the Python standard library; effective
configuration and raw command errors stay private. Helper presence is a warning,
not proof of registry login. Optional profiles/weights/readiness and custom Compose
overrides are outside its checks. This adds no multimodal quality/release gate.

- **58 new tests** use temporary files, fake command responses and an actual CLI
  subprocess with a fake Docker executable: missing plugin/daemon/env/helper,
  placeholders/permissions, actual application boolean forms, digest validation,
  timeouts, safe failures/exit codes, no secret echo and unchanged inputs.
- Backend non-integration regression: **632 passed, 398 deselected, 7.39s**. No
  database integration, native model or frontend change is implied by this count.
  The existing Starlette/httpx deprecation warning remains. The first restricted
  run stalled before a result and was interrupted; the rerun with local test
  permissions passed. No application service was restarted or deadline changed.
- Actual `docker compose config --format json`, with an allowlisted test-only
  environment, `/dev/null` env file and fresh disposable Docker config directory,
  matches the checker's default keyless validation. No daemon request or owner
  `.env`/Docker configuration was used for that probe; its empty directory was
  removed. Standard-library CLI help and whitespace checks also pass.
- Initial no-echo tests used `short`, which collided with the fixed word
  `shortcut`; unique synthetic sentinels corrected the tests. Independent review
  caught boolean/digest-validation differences from application settings; those
  were corrected and covered before the final regression.

Reproduce without Docker or application data: `backend/.venv/bin/python -m pytest
backend/tests/test_local_setup.py`. Operator usage and non-destructive startup
troubleshooting are in the README. The real-example human quality review remains
open; these software checks do not satisfy it.

## Existing-flow delivery recovery (2026-10-28)

Two frontend defects could discard an idempotent retry's identity after uncertain
acceptance. A failed chat conversation switch cleared the message key even though
the old conversation/draft remained. Subtitle and metadata forms used fulfilled
React form actions: returning an error state still reset uncontrolled fields,
forcing a newly keyed draft instead of replaying an already accepted request.

Chat now clears the key only after a validated successful switch to a different
conversation; failed or foreign-scope history preserves it. Reloading the same
conversation retains replay identity and deduplicates a returned saved turn.
Source forms submit explicitly, disable their own fields while pending, guard
duplicate dispatch and reset only after accepted success. Returned/rejected errors
keep the file/URL, rights, selected lesson and key. Playlist refresh cannot silently
change a retry's original association; accepted uploads stay accepted if source
refresh fails. These drafts are browser-local, not new persisted personal data.

- The new chat network/scope regressions and source returned-error regressions
  failed before their fixes, specifically exposing changed keys/reset controls.
- **12 new frontend cases** cover unchanged retry, successful and rejected scope
  switches, same-history replay, returned/rejected source actions, file/URL/rights/
  association retention, busy/removed playlist snapshots, pending/duplicate-submit
  controls, successful reset/new drafts and accepted-versus-refresh failure.
- Final frontend regression: **245 tests in 39 files passed, 5.05s**. Lint,
  typecheck and the optimized production build pass; the build uses test-only
  API settings without starting a service or calling a real model.
- No API/backend/schema, migration, provider, upload limit, rights policy or
  deletion behavior changed. Existing server authorization/idempotency remains
  authoritative. No owner settings, running services or application data changed.

The previous `7ea37cf` baseline has four successful jobs in
[run 40685623358](https://github.com/emredemirbas/multimodal-rag/actions/runs/40685623358).
That earlier run does not certify this recovery patch before its own hosted run.
No new quality/evaluator prerequisite is introduced; real-example review remains
open.

## Static keyless browser walkthrough (2026-10-28)

The new `/demo` page documents the existing workflow. Its guide component performs
no API calls, automatic project creation/upload/deletion or configuration changes.
It serves byte-identical
copies of `examples/fastapi-intro.vtt` and the root MIT notice, labels the synthetic
sample as having no recording, requires explicit licensed-content permission and
distinguishes record removal from confirmed retained-file cleanup. The standalone
Docker runner now includes `public/` so the downloads are actually available.

- **4 frontend cases** cover accessible guide/downloads, unchanged canonical sample
  and license, no render-time fetch/mutation, truthful limitations and Docker asset
  packaging. Full regression: **268 tests in 42 files passed, 4.82s**; lint and
  typecheck pass.
- **3 backend cases** use the real transcript chunker and default in-memory scoped
  retrieval/extractive service. Both supported questions quote the single published
  **00:01–00:22** chunk with stable generation-1 provenance; the unrelated Kubernetes
  question abstains without citations. This is not queue or database integration.
  Backend non-integration regression: **635 passed, 398 deselected, 11.00s**; the
  existing Starlette/httpx deprecation warning remains.
- An actual production frontend Docker build succeeds and prerenders `/demo`.
  A separate read-only, loopback-only disposable frontend container serves the guide
  in the browser and both sample downloads with HTTP 200 and exact canonical bytes
  (418-byte VTT, 1,071-byte license). Browser accessibility output and the rendered
  page were inspected. Its API points only to an unused loopback port, not the
  owner's backend; this checks static serving, not full application readiness.
  The temporary tab/container were removed; owner services, settings and data were
  untouched. No model or native-media call was made.

The previous `571480b` baseline has four successful jobs in
[run 40700471893](https://github.com/emredemirbas/multimodal-rag/actions/runs/40700471893).
It does not certify this subsequent change before its own hosted run. This guide
does not select the release finish line, start Sprint 5 or close the independent
owned/licensed real-example quality gate.

## Live source filters without losing chat state (2026-10-28)

Project details previously passed independent initial source snapshots to chat and
source management. Processing could finish in the visible source list while chat
still required a full page reload. A small project-keyed client wrapper now shares
only successfully parsed source/playlist refreshes with chat, using the existing
poll and Refresh sources request. No second poll, router refresh, provider call or
API/schema/authentication change was added.

Missing or incompatible selected sources stay explicitly selected as unavailable,
with an accessible explanation. New questions require an explicit filter choice;
an unchanged uncertain-delivery retry keeps its original source and key. Inventory
updates do not remount chat or rewrite saved citations/generations. Project changes
remount the scoped wrapper; a late old-project refresh cannot publish into it.
The demo guide no longer requires a reload after processing becomes ready.

- **10 new frontend cases** cover ready publication through the existing poll,
  network/invalid-source/invalid-playlist refresh failures, a pending chat across
  generation replacement with unchanged replay identity, late old-project delivery,
  removed/incompatible selected filters, explicit all-source selection, unchanged
  retry after source disappearance and stable old evidence during reprocessing.
- Full frontend regression: **278 tests in 43 files passed, 8.19s**; lint and
  typecheck pass. An initial render-time ref read was rejected by the existing
  React lint rule; retry availability now uses state while the event handler checks
  the authoritative replay ref. No rule was disabled.
- The actual production Docker frontend build passes. A browser probe against
  that image and a separate GET-only synthetic API fixture shows processing ->
  ready, the newly selectable source and the unchanged question draft without a
  page reload. It does not test a real queue, database, model or media input. The
  fixture API stayed on a dedicated internal network; only the separate frontend
  had a temporary loopback host port. No real credentials, application mounts,
  volumes or owner services/data were used. Both temporary containers, both test
  networks and the browser tab were removed after the check.

Reproduce the component checks with `cd frontend && npx vitest run
src/components/projects/project-evidence-workspace.test.tsx
src/components/chat/chat-workspace.test.tsx`. Independent review found no blocking
scope/replay/accessibility issue. The real-example quality gate and unselected
release finish line remain unchanged.

## Source-removal consistency in open chat (2026-10-29)

The existing PostgreSQL source-delete trigger removes each complete chat turn
citing the deleted source, including quoted answer text. The mounted browser had
kept displaying its old copy until history reload. This was stale client output,
not a cross-tenant disclosure or a failure of the server-side deletion cascade.

A project-keyed, monotonic removed-source fence now hides those complete turns by
their citation dependencies, including all-source questions and mixed-source
answers. Confirmed same-project deletion updates the source card/chat immediately,
even if the follow-up inventory fails. Successful complete inventory snapshots also
detect missing known sources. Initial source-load errors are not empty-inventory
proof; reindexing, generation changes and unrelated/unsupported turns are retained.
Stale source snapshots cannot resurrect removed cards or chat selections.

Chat masks partial delivery on removal, aborts the browser request and checks a
request epoch after asynchronous history/SSE completion. Late responses cannot
re-display removed evidence. The question/filter and uncertain replay identity
remain intact; browser abort does not claim to cancel already committed work.
This is a browser-view fence, not secure erasure of already received/copied data or
confirmation of independently tracked physical object cleanup.

- **13 new component cases** cover whole/mixed/all-source turn removal; preservation
  of unrelated history, limitations and draft; confirmed delete with failed refresh;
  failed/foreign-project receipts; a pre-delete GET arriving late; authoritative
  missing-source snapshots and subsequent stale snapshots; initial source errors;
  late history/partial/SSE completion; exact unchanged replay and project-scope reset.
- The three new direct-chat regressions failed before the fix. A separate
  initial-error -> valid-empty -> stale-source test exposed card resurrection before
  adding known initial citation IDs to the source-list fence. Both then passed.
- Full frontend regression: **291 tests in 43 files passed, 16.38s**; lint,
  typecheck and actual production Docker build pass. No rule was disabled. Existing
  backend contracts/auth, database migrations, queue, provider and retention policy
  were unchanged; no new backend/integration/model-quality result is implied.
- A browser probe against the production frontend and a separate GET-only synthetic
  API first displayed an authored answer/citation, then a successful full missing-
  source snapshot removed both without losing the typed draft. Reload history
  deliberately returned the old answer again; the view fence kept it hidden. The
  fixture used no actual delete request, real application data/credentials, database,
  models or owner services. Its API stayed on its own internal network; only its
  separate frontend had a temporary loopback host port. Both test containers,
  networks and the temporary tab were removed after the check.

Independent code review found no blocking scope, retry, race or accessible-state
issue. The previously pushed `ba4710a` baseline is separately green in all four
jobs of [CI run 40707364988](https://github.com/emredemirbas/multimodal-rag/actions/runs/40707364988);
that run does not certify this subsequent patch. The independent real-example
quality gate and the owner's release finish-line choice remain unresolved.
