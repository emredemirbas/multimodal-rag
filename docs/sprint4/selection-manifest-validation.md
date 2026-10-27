# Versioned selection-manifest verification

Date: 2026-10-27. Scope: ADR 0027/migration 0018, private contract/persistence and
public origin/UI compatibility. Managed native production remains uniform v1.

## Software evidence

- **35 new contract tests**: unchanged golden legacy wire/digest, v2 roundtrips,
  fixed identity/policy/protocol pairing, temporal returns, 600-sample/20-point
  limits, static/noisy/change ranking agreement, fractional source-FPS/tail bounds,
  malformed geometry/hash/scores/types, missing/reordered/partial scans, tampered
  selections/frames and mutated nested lists. Combined with the original scene
  component: **74 passed, 0.22s**. The shared ranking preserves the prototype.
- PostgreSQL tests cover complete manifest/frame/digest transactions, stale-lease
  recovery without reselection, unselected hash/score corruption, schema/selection
  corruption, missing/oversized/v1 manifests, final-fence rollback and an unchanged
  legacy result across a reconstructed exact pre-0018 column/constraint upgrade.
  Fresh/Sprint-0 and older upgrade/checksum tests include the new migration.
- The original 13 scope/actor/token/generation/membership/cancel/expiry/deletion
  fence cases now also run with v2. A synthetic v2 producer goes through actual
  prepare/raw cleanup -> six retained temporal frames -> indexed OCR -> versioned
  citation/evidence -> reindex with unchanged old evidence -> complete project
  deletion. Usage preserves profile/selected-frame attribution and zero billing.
  Public JSON omits private scan hashes/scores; checkpoint logs omit both scan
  payloads and OCR text. The authorized gallery still intentionally shows OCR.
- **816-test full backend regression passed, zero skipped, 185.24s**, including
  actual worker-loss/recovery probes with `TEST_REAL_WORKER=1`. The subsequently
  added maximum-600-sample concurrent-begin/save case passed with the complete
  new integration file: **11 passed, 3.79s**. Thus **817 distinct backend cases**
  are covered across those runs; do not describe this as one 817-test command.
  One upstream Starlette/httpx TestClient warning remains unsuppressed.
- **172 frontend tests passed** in 31 files (7.95s); lint, typecheck and production
  build also pass. Three new tests cover profile/checkpoint pairing, honest
  temporal-return/change-selection notices and citation provenance. Existing
  accessible image loading/error/retry, literal OCR and empty states remain.

The first targeted integration run had 132 passing cases and one stale expected
migration-list failure; only that expectation was updated. A subsequent full run
had 806 passes before its test-only PostgreSQL 1 GiB tmpfs filled with WAL, causing
11 teardown/setup errors. The test helper was changed to use a fresh 2 GiB tmpfs
and 3 GiB memory limit **only for its disposable PG container**; the unchanged
assertions then passed as recorded above. No product disk/memory settings or
timeouts were increased. New random-port PG/Redis/MinIO containers used only
allowlisted test credentials and no app `.env`/volumes; only their recorded IDs
were removed. Initial sandboxed loopback tests hit `EPERM`; the full regression
ran with normal local socket permissions, without weakening native isolation.

The initial sandboxed frontend build compiled but could not parse its TypeScript
child-process output. The same sources passed the normal-permission build; no
dependency, compiler setting or check was disabled. The final legacy omission
serializer uses the existing supported Pydantic wrapper API, not a new minimum
dependency requirement.

## Actual unchanged native regression

Built a separately tagged minimal native image including the pure manifest module.
The final image passed both existing isolated probes in new non-root/network-none/
read-only containers: 192 MiB tmpfs, 1 GiB RAM/no extra swap, two CPUs, 32 PIDs,
no capabilities/new privileges/core dumps, no host mounts or app credentials.

- The authored transient comparison still retains baseline `[0]` versus candidate
  `[0,3000,4000,7000,13000,19000]`, with the same prototype identity/clip digest,
  temporal return, safe CLI rejection and `quality_approval=not_established`.
- The actual private HTTP/OCR test still returns uniform v1 four candidates/two
  frames at `[0,10000]`, with literal PNG/OCR transport, profile pinning and kernel/
  child network denial. Application records created by these probes: zero.

These are not native v2 OCR, representative scene/code quality, a new ten-minute
performance result or full Sprint 4/Alpha 2 validation. The v2 producer used in DB
tests is explicitly synthetic. Actual fractional-rate extraction and a pinned
service/worker v2 end-to-end test remain the next gate.

## Delivery boundary

All earlier applied migration files remain unchanged. No migration was applied to
the owner's app; no running app service, upload flag, original user data or `.env`
was changed. No model download, paid call or new provider was used. The separately
verified hosted baseline is `d46a0a76c29bf1ddb31076273aba90b842989968`, all four jobs
successful in [run 40566345896](https://github.com/emredemirbas/multimodal-rag/actions/runs/40566345896).
This is not a hosted result for the subsequent manifest commit; verify its exact
SHA separately after push.
