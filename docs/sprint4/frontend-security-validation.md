# Next.js and Vitest audit remediation validation

Date: 2026-10-23

## Actual failure

[Run 39958139717](https://github.com/emredemirbas/multimodal-rag/actions/runs/39958139717)
for media-inspection commit `2fc566a` passed both backend jobs but failed in
`Check dependency advisories`. Frontend lint/typecheck/tests/build did not run;
the dependent image job was skipped. The three vulnerable packages reported were
Next.js (critical), `@vitest/mocker` (moderate) and its dependent Vitest (moderate).
The Node action-runtime deprecation and Ubuntu notices did not cause this failure.

The earlier media-inspection report remains local software-test evidence, not a
claim that hosted CI or an up-to-date dependency audit had passed for that commit.

## Scoped remediation

- Next.js **16.3.8 → 16.4.2**, with matching **eslint-config-next 16.4.2**.
  The maintainer's fixed 16.x line starts at 16.4.1; 16.4.2 is a subsequent stable
  patch on that line. Keep React unchanged. Installed image handling uses
  `sharp@0.35.5`, meeting the maintainer's patched dependency floor.
- Vitest **4.1.11 → 4.1.12**, including its matching 4.1.12 internal packages and
  patched mocker. npm also resolves compatible `chai`/`tinyrainbow` test-transitive
  updates; no blanket dependency update or forced audit fix is used. Vite remains
  pinned at 7.3.7; no Vitest 5 migration.
- Advance only the lint adapter's exact plugin override/version assertion to
  `@next/eslint-plugin-next@16.4.2`. Inspect the installed plugin: it still has the
  one `globSync(rootDir, { onlyDirectories: true })` call in `get-root-dirs.js`.
  Keep the private maintained-library adapter and existing framework, TypeScript
  and accessibility rule checks. No vulnerable glob dependency is reintroduced.
- Regenerate the lockfile using npm and verify a clean `npm ci`. CI's full-tree
  audit threshold and all subsequent checks remain unchanged; no ignored advisory,
  removed rule or workflow bypass.

Maintainer advisories:
[Next image optimization](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw),
[Server Actions](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r),
[cache handling](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr),
[Vitest manual mocks](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8),
[Vitest redirects](https://github.com/vitest-dev/vitest/security/advisories/GHSA-xp26-3454-mjgp).

## Local validation

- Clean `npm ci --no-audit --no-fund`: passed.
- Full `npm audit --audit-level=high`: **zero vulnerabilities** at validation time.
- Installed tree: Next/config/plugin 16.4.2, sharp 0.35.5, Vitest/mocker 4.1.12;
  Vitest and React test plugin share the pinned Vite 7.3.7 instance.
- Lint compatibility, lint and typecheck: passed on the local Node 20.19.6 runtime.
- Frontend **20 files / 77 tests**: passed.
- Production Next.js 16.4.2 build: passed with normal local process permissions.
- Production frontend Docker build: passed with the CI-pinned Node 24.21.0.
- CI-pinned Node **24.21.0** builder container, networking disabled and no
  application credentials/data mounts: **all 5 lint-compatibility tests**, lint,
  typecheck and **20 files / 77 frontend tests** passed. The real production
  runtime image separately reports Next.js **16.4.2**.

Hosted CI is a separate check, not inferred from either local runtime. This record
contains the pre-push evidence for the corrective commit; its new hosted result
must be checked independently.

Follow-up: corrective commit `d491796` passed all four jobs in
[run 39959500922](https://github.com/emredemirbas/multimodal-rag/actions/runs/39959500922)
(backend tests, backend integration, frontend and production images). This confirms
that corrective commit only, not subsequent audio-upload work.

No application code, schema, authorization policy, media scope or paid provider
changes. WAV uploads remain disabled. No backend tests are rerun locally for this
frontend-only dependency fix; hosted CI independently exercises them. Application
containers are not restarted, user data/queues/volumes are untouched, and `.env`
remains unchanged/ignored with mode 0600. Test-only containers have no application
credentials or data mounts; no model weights are downloaded.
