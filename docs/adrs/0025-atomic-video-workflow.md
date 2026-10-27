# ADR 0025: Atomic private video-to-OCR handoffs

- Status: Accepted continuation of ADRs 0021–0024
- Date: 2026-10-27

Add an explicitly opted-in private registration mode, not a public MP4 endpoint.
Persist a fully scoped workflow with original input/job/actor, policy version,
embedding target and derived child identities. Existing manual registrations and
their request hashes remain unchanged. The automatic/manual choice is part of
request identity; replay never changes the accepted embedding target or recreates
an original.

Use the existing PostgreSQL/outbox/Celery machinery, not LangGraph or another
queue. Preparation, usage, raw retirement and gallery job/outbox commit together.
Complete gallery publication and OCR index job/outbox commit together. The final
parent wall-clock check covers child creation too. Rollback leaves neither an
unpublished child nor a completed parent stranded between stages. S3 candidate
writes retain their independent unique orphan reservations. Broker redelivery is
fenced by current source generation; inference in flight may still repeat.

Pin the configured embedding space at acceptance, not at the visual worker's
handoff. Restore a matching provider before retrying a configuration failure;
never relabel vectors, download weights or select a paid fallback automatically.
An accepted workflow may continue on an archived project; new uploads/manual
commands still require active status. Archive is not cancellation. Cancellation
and revocation fence the current job before another handoff. Only the original
initiator can retry derived automatic work; ordinary authorized gallery/evidence
inspection remains tenant-scoped. Extraction terminal paths require a new upload.

No format, language, TTL, retention, quality or provider gate changes. Keep public
upload/reprocess closed. Existing source status follows the current child; the
accessible upload and raw-cleanup UI are the next bounded product slice. Workflow
metadata cascades on complete deletion. See `../sprint4/video-workflow-plan.md` and
`../sprint4/video-workflow-validation.md`.
