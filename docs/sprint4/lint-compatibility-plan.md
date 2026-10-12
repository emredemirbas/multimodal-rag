# Lint dependency remediation plan

Date: 2026-10-11
Status: Implemented and validated from clean npm installation; full audit has
zero findings. All 5 compatibility tests, lint and production build pass.

The owner asked to continue after the reported development-only `braces` audit
blocker. Upstream still has no fixed package version. Do not suppress the finding,
downgrade Next, remove framework/accessibility rules or relabel vulnerable code.

The pinned `@next/eslint-plugin-next@16.3.8` uses one dependency call:
`globSync(pattern, { onlyDirectories: true })` to resolve configured root directories.
Replace only that dependency with a private application-owned compatibility
package backed by pinned official `tinyglobby@0.2.17`. The maintained library has
no `braces`/`micromatch` dependency. It is not a fully compatible fast-glob alias:
literal directory expansion must be disabled, absolute-result shape retained,
and directory suffixes normalized. Unsupported options fail closed for review
when upgrading Next; configuration pattern length/nesting is bounded.

This tooling decision does not select an LLM/ASR vendor, enable model calls or
expand media retention. No schema, ingestion or user data changes are required.

Validate clean `npm ci`, the actual upstream root helper for literal/glob/array
configuration, and deliberately invalid code against unchanged Next Core Web
Vitals, TypeScript and accessibility rules. Keep compatibility checks in CI and
verify that vulnerable dependencies are absent from the lockfile/install tree.
Then run full audit, frontend tests/lint/typecheck and Docker build/smoke checks.

References: [maintained library migration guide](https://superchupu.dev/tinyglobby/migration),
[API/options](https://superchupu.dev/tinyglobby/documentation),
[upstream braces issue](https://github.com/micromatch/braces/issues/70).
