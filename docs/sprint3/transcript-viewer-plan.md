# Version-pinned transcript browsing

Date: 2026-10-14
Status: Implemented and locally validated; see `transcript-viewer-validation.md`.

Continue the existing source/evidence UX without enabling binary media, paid calls,
new retention, implicit conversation context or later assignment work. Users can
read an uploaded tutorial without first obtaining a chat citation.

Material assumptions:

- Browse only published transcript segments, never embedding checkpoints, frames
  or metadata presented as tutorial evidence. Reading does not require the current
  embedding space and invokes no model or object-store calls.
- The initial request chooses the active generation. Every subsequent page pins
  that generation explicitly; old successful generations remain readable after
  reprocessing. An unfinished replacement cannot become a browsable generation.
- Fixed pages of 50 segments ordered by start/end time and stable ID. Durable
  uploads keep the existing 10,000-chunk cap; browsing allows up to 2,000 pages
  for older validation-only inputs (one segment/cue under the existing 2-million-
  character body limit). No processing limit is raised. Reject later pages without an explicit generation.
  A repeatable-read, read-only snapshot keeps source metadata/count/page consistent
  within a request without blocking workers with a project write lock.
- Enforce authenticated membership, tenant, project and source scope on every
  read. Archive permits inspection; deletion/revocation prevents subsequent reads.
- Add an index-only migration for scoped chronological reads. Existing evidence
  and applied migrations remain unchanged. Existing safe route metrics/logging
  cover these read-only requests; no inference usage is fabricated.
- Accessible server-rendered timeline, loading/empty/error states, bounded page
  navigation, stable evidence links and explicit older-generation wording. Render
  untrusted text with React escaping, not HTML or Markdown execution. No player or
  download URL is invented for subtitle uploads.

Verify PostgreSQL ordering/pagination/snapshot behavior, auth/isolation, legacy and
mixed-space evidence, private staging exclusion, reprocessing and deletion; UI
contracts/navigation/text safety; real worker + production SSR smoke and existing
regressions. Preserve user data/configuration. No commit/push without a new request.
