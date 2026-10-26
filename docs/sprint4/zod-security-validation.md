# Transitive Zod audit follow-up

Date: 2026-10-26
Status: Targeted correction implemented; local checks recorded below. Corrective
hosted CI remains a separate check, not inferred from the previous failed run.

Visual commit `7f0ee79` passed both hosted backend jobs in
[run 40338181380](https://github.com/emredemirbas/multimodal-rag/actions/runs/40338181380)
but failed `Check dependency advisories`; the dependent image/native visual job
was skipped. Do not call that run or its native visual gate passed. The local
native evidence remains separately recorded in `local-visual-validation.md`.

The full npm audit now reports high-severity
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
for Zod <4.6.6. This checkout has **4.6.5** as a development-only transitive of
`eslint-config-next@16.4.2 -> eslint-plugin-react-hooks@7.1.1`; its dependency and
`zod-validation-error` peer both allow the patched 4.x line. This is an advisory
failure, not an OCR test failure or the Node action-runtime warning.

Select a targeted same-minor lockfile update to published **4.6.7**, above the
maintainer's 4.6.6 fix. Do not add a direct runtime dependency, upgrade Next/React,
loosen the lint adapter, disable audit or force a blanket dependency change.
Verify the exact lock diff, clean install, full audit, lint compatibility/rules,
typecheck, all frontend tests and the production Node 24 image. No application
code, database/data/media policy or actual `.env` change is required.

Maintainer implementation: [early size-bound checks](https://github.com/colinhacks/zod/commit/a0ebf970f2d752e5f58527cd2942ff48be4f46bd).

## Local evidence

- `npm update zod --package-lock-only --ignore-scripts`: only the existing
  development-only `node_modules/zod` version/tarball/integrity changed (4.6.5 →
  4.6.7). `package.json` and every other package/version are unchanged.
- Clean `npm ci`: passed; installed tree uses deduplicated Zod 4.6.7 within the
  existing React-hooks/validation-error ranges.
- Full-tree `npm audit --audit-level=moderate`: **zero vulnerabilities** at check.
- Local Node **20.19.6**: all five pinned lint-compatibility/rule tests, lint,
  typecheck and **22 files / 104 frontend tests** passed.
- Clean production frontend builder image with CI's Node **24.21.0**: passed.
  No application credentials/data mounts or application-service restart.
- Same Node **24.21.0** builder in an ephemeral network-disabled test container:
  all five lint-compatibility tests, lint, typecheck and **104 tests** passed.

The full backend/native visual validations remain recorded separately; this
corrective commit changes no Python/media code or schema. CI must independently
run all four jobs, including the previously skipped optional visual image/smoke.
