# Vite security patch validation

Date: 2026-10-21

## Failure and scoped fix

The [hosted run for `32489e1`](https://github.com/emredemirbas/multimodal-rag/actions/runs/39650520144)
passed both backend jobs but failed at `npm audit --audit-level=high` in the
frontend job. The audit reported one high-severity vulnerable package,
`vite@7.3.6`, including bundled launch-editor and Vite advisories. Frontend checks
after the audit and the dependent image job did not run. The Node action-runtime
and Ubuntu runner notices were not the failing step.

Pin only Vite **7.3.6 → 7.3.7**, the patched 7.x release, and regenerate its
lockfile entry/integrity from npm. No unrelated package upgrades, forced audit
fix, audit exceptions, removed checks or workflow changes are included. Vitest
and the React test plugin resolve to the same patched Vite instance.

References: [Vite custom-middleware advisory](https://github.com/advisories/GHSA-9jrq-w75r-8gcw),
[Vite filesystem advisory](https://github.com/advisories/GHSA-rq7h-c2jc-7f22).

## Local verification

- Clean `npm ci --no-audit --no-fund` succeeds from the updated lockfile.
- `npm audit --audit-level=high`: **zero vulnerabilities** across the full tree.
- `npm run test:lint-compat`: **5 passed**; framework/accessibility rules remain active.
- `npm run lint` and `npm run typecheck`: passed.
- `npm test`: **17 files / 60 tests passed**.
- `NEXT_TELEMETRY_DISABLED=1 npm run build`: production build passed.
- `docker compose build frontend`: passed with the CI-pinned Node **24.21.0**;
  its clean npm installation also reports zero vulnerabilities.

No application behavior, schema, authorization, ASR capability, credentials,
running services or user data is changed. Backend tests are not rerun locally
for this development-tool-only patch. Hosted CI is a separate check; the results
above are local evidence, not a claim that a subsequent hosted run passed.
