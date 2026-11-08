# Public repository review

Date: 2026-11-08. Reviewed starting application commit: `133bbb3`.
The repository remains private; visibility is an owner action, not part of this
review. This checks repository publication hygiene, not production readiness or
the unresolved native assignment-quality gate.

## Product presentation

- README describes working transcript ingestion, scoped chat, stable evidence,
  local installation, optional model/media paths and their limitations. Internal
  sprint, acceptance, CI-run and test-count records remain in `docs/`.
- Added the normal workflow-status badge and clarified that assignment generation
  is under development and unavailable in the workspace; submissions/grading are
  not implemented. No hosted demo or unsupported feature is advertised.
- Set the GitHub description to: “Local multimodal RAG workspace for programming
  tutorials with timestamped citations, project-scoped chat and optional local
  models.” Added matching stack/product topics; no fictitious homepage URL.
- MIT source license and the authored sample licenses remain. Uploaded material
  and model weights are not relicensed by the source-code license.

## File and history inspection

- Enumerated 57 reachable commits and all 1,272 unique reachable file blobs,
  including deleted/earlier versions and root commits. No historical `.env`,
  private-key/certificate, database, backup, log, archive or real binary media
  path was found. `.env.example` contains placeholders, not the local values.
- Scanned Git history, the tracked HEAD export and all exported historical blobs
  with official [Gitleaks v8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1),
  verifying the downloaded archive against its release checksum and redacting
  reports. Git diff history produced two findings, HEAD one, and complete blob
  enumeration four: all versions of the same smoke-test false positive.
  The adjacent Python arguments `idempotency_key` and `retention_acknowledged`
  build a test request; they are not a literal API credential. No scanner rule was disabled and
  no broad allowlist was added to hide warnings.
- Compared three non-placeholder local credential values in memory against every
  historical blob; no match. Values were not printed or copied into the report.
  Local `.env`, dependencies, caches and build output remain outside Git.
- The retained native-output JSON and tutorial fixtures are explicitly authored
  MIT demonstration data, not private tutorials or user transcripts. Technical
  ADRs, tests, `AGENTS.md` and validation documents are useful public project
  material and are retained.
- Removed the obsolete personal `CODEX_KICKOFF.md` from the current index while
  preserving the local file. It contained a machine path and stale sprint
  instructions. Ignoring/untracking does not erase its earlier Git versions.
- Added ignore patterns for key files, credential exports, local databases,
  backups, logs, model weights and private/local-data directories. Source files,
  migrations, `.env.example`, licenses and authored fixtures stay trackable.

## Commit-email privacy

Existing history contains the owner's personal author/committer address. The
owner requested a separate privacy plan; history was not rewritten and no force
push was performed. The plan and email mapping are local-only under the ignored
`private/publication/` directory, with private file permissions. New publication
changes use the verified account's ID-based GitHub noreply address.

**Before making the repository public:** complete the chosen email-privacy
migration if the personal address must remain private. A `.mailmap`, ignore rule
or new noreply commit alone does not remove old author metadata. The private plan
distinguishes a clean repository migration from rewriting the existing remote,
including retained old objects/cached views. No file-content secret was found by
the checks above; this does not make the pending email-privacy step complete.
