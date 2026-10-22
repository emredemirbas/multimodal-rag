# Durable local WAV processing (private backend slice)

Date: 2026-10-22
Status: Implemented and locally validated; see `media-worker-validation.md`.
Product WAV upload remains disabled until the UI/BFF slice.

The owner requested push followed by continued development and authorized future
tested, scoped commit/push delivery without another confirmation. No force push,
secrets, unrelated changes, paid calls or expanded media scope is authorized.

- Register owned/authorized/licensed supported WAV internally, with scoped
  idempotency, a write-ahead orphan reservation and a separate temporary-original
  record. No public WAV API/form is enabled by this backend component.
- Safety assumption: originals expire after one hour even if a queue is abandoned.
  Stop processing expired/revoked/terminal work and schedule observable cleanup.
  Physical deletion is confirmed only after the object store succeeds; exhausted
  cleanup remains visibly failed/retryable, never described as already deleted.
  Expiry stops processing eligibility; scheduler/storage outages can delay actual
  deletion until dependencies recover.
- Use a dedicated optional media worker and `media` queue. Ordinary workers do
  not register the media task; scheduler routing accepts only known job types.
  The model service remains isolated/credential-free and receives PCM/language only.
- At most one 30-second window per delivery, existing lease/soft/hard limits,
  checkpointed continuation without consuming failure retries. Resume committed
  windows after process loss, not in-flight inference. Preserve bounded retries.
- Adopt only a complete validated VTT under a live fence. Use a unique candidate
  prefix/write-ahead cleanup reservation per attempt so a stale orphan cleanup
  cannot delete a later adopted artifact. Recheck authorization after object PUT.
- Atomically retain the VTT, complete ASR, record actual local usage/provenance,
  enqueue ordinary transcript indexing and retire the original. No partial index
  or citation is published. Reindex uses retained VTT; retranscription requires
  re-upload after original retirement. Cancel/permanent failure also retires audio.
- Keep the ASR job/profile linked to derived artifacts and every processing
  generation. Preserve complete source/project deletion, safe logs/metrics and
  current SRT/VTT behavior. Test actual queue/process-loss/MinIO cleanup separately
  from fixture inference and native model quality.

The original cleanup and orphan lifecycle use the existing durable scheduler.
Uploads remain unavailable until bounded authenticated BFF/API/form, explicit
rights/language/retention guidance and machine-generated inspection UI are verified.
