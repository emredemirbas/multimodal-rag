# Frontend audit remediation

Date: 2026-10-23
Status: Implemented; local validation and hosted verification are recorded in
`frontend-security-validation.md`.

The owner supplied the failed CI screenshot after `2fc566a`. Run `39958139717`
passed backend checks but failed at the full-tree `npm audit --audit-level=high`
gate, before lint/tests/build. Node action-runtime notices are not the cause.

The audit and maintainer advisories identify Next.js runtime vulnerabilities
(image optimization, Server Actions denial of service and typed-array cache
handling) and two development-only Vitest mocker vulnerabilities. The Next.js
fixed line begins at 16.4.1; pin published 16.4.2 and matching ESLint configuration.
Pin Vitest 4.1.12, the fixed 4.x release. Keep React, Vite, audit thresholds and
framework/accessibility rules unchanged; do not run a forced or blanket update.

Advance the narrowly pinned lint-glob override only to the newly inspected Next
plugin, verify its dependency call and existing root-resolution/rule compatibility
tests from a clean installation. Regenerate the lockfile through npm, inspect the
tree for actual patched Next/sharp/mocker versions and check full audit, clean
install, lint, typecheck, all frontend tests and production Docker build. Preserve
source/chat/upload behavior and keep model/media/public-upload gates unchanged.

Record local results separately from hosted CI, then commit/push under the owner's
standing authorization and verify the new run. No DB/schema/model-call/user-data
change or application-service restart is needed for this fix.

Maintainer references:

- [Next image optimization](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
- [Next Server Actions](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r)
- [Next cache handling](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr)
- [Vitest manual mocks](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8)
- [Vitest path normalization](https://github.com/vitest-dev/vitest/security/advisories/GHSA-xp26-3454-mjgp)
