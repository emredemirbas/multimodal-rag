# Public repository review

Date: 2026-11-08. Reviewed application baseline after privacy migration: `f7c85c1`.
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
- Removed the obsolete personal `CODEX_KICKOFF.md` from the published index and
  all published historical versions while preserving the ignored local file.
  It contained a machine path and stale sprint instructions.
- Added ignore patterns for key files, credential exports, local databases,
  backups, logs, model weights and private/local-data directories. Source files,
  migrations, `.env.example`, licenses and authored fixtures stay trackable.

## Commit-email privacy

After approving the privacy plan, the owner authorized its completion. A separate
mirror was rewritten with official `git-filter-repo` 2.47.0, replacing the personal
author/committer email with the verified account's GitHub noreply address and
removing every historical version of the obsolete kickoff file. All 58 commits
were compared with their originals: parent relationships, names, dates, messages
and source trees were preserved except for the approved file removal. The latest
source tree was identical. One old GitHub signature was removed because rewritten
commits cannot retain its validity.

The original repository was retained as the private
`emredemirbas/multimodal-rag-private-history` archive. An independent, empty private
repository was created at `emredemirbas/multimodal-rag` for a normal initial push
of the clean `main` history. No force push or fork relationship was used. Only
`main` is published; private backups, mappings, audit exports and editor refs are
not transferred. The active checkout uses the clean history and a repository-local
noreply email setting, without resetting working files or changing `.env`, data,
Docker settings or running services.

The clean history and all 1,274 reachable file blobs were scanned again with the
checksum-verified Gitleaks release. The same two diff/four blob smoke-test false
positives were confirmed; no additional finding appeared. Every reachable commit
identity uses GitHub noreply metadata, and the personal email is absent from commit
messages and file contents. Local private files were checked unchanged.

Old commit hashes and CI references elsewhere in `docs/` describe the archived
history. They do not establish the new repository's CI result; use its current
GitHub Actions run. The private archive, verified local bundle and local reflogs
still retain original metadata and must remain private. Do not push or merge old
history back into this repository. Visibility remains an owner action; this review
does not change the owner's GitHub account email-privacy settings.
