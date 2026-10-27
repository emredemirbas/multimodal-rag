# Opt-in native change-aware OCR verification

Date: 2026-10-27. ADR 0028; existing v2 storage contract/migration 0018.
Default uniform and upload opt-ins are unchanged. No broad quality/Alpha 2 claim.

## Software evidence

- **37 new backend cases**: fixed two-pass native coordination; complete scan/
  selection/temporal returns; missing/extra/aliased/symlink/non-file/oversized/
  wrong-geometry/deadline outputs; invalid input/language/isolation before native
  work; HTTP language/policy pins, wrong/unavailable/tampered profiles and strict
  query rejection; no payload logging; explicit/default configuration isolation;
  both policy directions across incomplete/saved checkpoint recovery; unpinned
  worker selection. The combined targeted regression passed **149 tests, 12.50s**.
- Final full regression: **854 passed, zero skipped, 185.56s**, with actual worker
  process-loss probes (`TEST_REAL_WORKER=1`) and fresh random-port PG/pgvector,
  Redis and MinIO services. Test-only environment/credentials/tmpfs; no application
  `.env`, queues, bucket or volumes. Only recorded new containers were removed.
  One upstream Starlette/httpx TestClient warning remains unsuppressed.
- An earlier full run had **853 passes and one 30-second replacement-gallery-
  worker timeout** (238.88s). The unchanged exact test then passed alone in 3.31s,
  followed by the successful final full run above. Root cause is not established;
  do not suppress the failure or claim a proven product fix. No assertion, timeout,
  retry bound or isolation check was weakened.
- **172 frontend tests** pass in 31 files (4.52s), including the upload scope text
  assertion. Lint/typecheck and the production Docker build pass. Existing loading,
  error, retry, literal OCR, gallery/citation origin and empty states remain.

No schema is added or earlier migration edited. Existing tenant/project/actor/
generation/cancellation/membership/expiry/deletion and legacy wire/digest tests
remain in the full suite. Native parsing remains absent from ordinary workers/API.

## Actual isolated native evidence

Built the minimal native image separately, then ran new non-root/read-only/
network-none containers: 192 MiB tmpfs, 1 GiB RAM/no extra swap, two CPUs, 32 PIDs,
no capabilities/new privileges/core dumps, no host mounts/credentials. The service
binds its private listener before inherited kernel socket denial; child denial is
still verified. Existing native child/aggregate budgets are unchanged.

Actual private HTTP, full-size frame OCR, complete manifest and operator CLI pass.
All authored inputs contain a short contrasting view around 3–4s and a return:

| Verified source FPS | Scan count | Actual selected/result PTS in ms |
|---|---:|---|
| 2 | 20 | 0, 3000, 4000, 7000, 13000, 19000 |
| 30000/1001 | 20 | 0, 3003, 4004, 7007, 13013, 19019 |
| 1001/1000 | 10 | 0, 3996, 5994, 13986, 17982 |

Each has exact scan/result PTS equality and recognized brief-view OCR. The 2fps
case preserves the equal-pixel return at 4000ms; the same clip's actual uniform
pipeline retains only `[0]` and misses that view. Native profile is
`local-visual-v2:6be8762315e8ced16cbb4a032662549baceb6435c24207de82f95285d263d5b3`.
The unchanged private uniform HTTP/OCR smoke also passes: four candidates/two
retained bilingual-card frames at `[0,10000]`. Native probes create no app records.

Initial test-fixture attempts exposed two authoring problems, not production
limits to increase: high-FPS all-I-frame output exceeded the existing 2 MiB native
file cap, so fractional fixtures now use a bounded GOP; FFmpeg's default output
sync rounded a requested 1.001fps fixture to 1fps, moving its text across the
declared interval. Explicit passthrough/rate and encoded-FPS assertions correct
the fixture. Exact production PTS and OCR assertions remain intact.

These are authored high-contrast text views, not representative code/terminal,
semantic scene, sub-second or OCR-quality benchmarks. No native 10-minute/high-
bitrate performance result. Complex clips may exceed unchanged limits.

## Actual managed public workflow

Used a newly named Compose project, validated new nonexternal volumes, random
loopback ports and allowlisted test-only settings (`--env-file /dev/null`). Native
service still has no environment, mounts or published ports and only an internal
network. Built current API/worker/native/frontend test images; no owner service
was restarted or configured. Tested both policies explicitly on that fresh stack:

- Uniform bilingual cards retain `[0,10000]` with the existing OCR/citation flow.
- Change mode uses the 2fps authored transient, persists all 20 scan records and
  six selected exact PTS, including the temporal return. Public multipart BFF/API
  upload and idempotent replay proceed through actual Celery extraction -> atomic
  gallery/outbox -> OCR index. A source-filtered question cites the brief OCR at
  **3000ms**, with matching v2 origin/frame ID, SSR experimental notice and protected
  PNG. Usage remains zero-billed. This is not a quality score extrapolated from it.
- Each owned project confirms raw-video deletion, retains only its allowed frame
  objects, then confirms complete relational/manifest/object cleanup and evidence
  404 after deletion. The helper removes only its validated fresh Compose project
  and volumes. No 100 MB native processing claim is added by this smaller probe.

CI now runs the fractional native check and both managed policies explicitly,
restoring its worker default after the change smoke. Owner `.env`, media/data,
running stack and opt-in flags remain untouched. No paid call or model download.

The separately verified hosted baseline is
`f7196356ad9297d2be1e59e5b082ce665b3e66d6`, all four jobs successful in
[run 40569511282](https://github.com/emredemirbas/multimodal-rag/actions/runs/40569511282).
That result does not certify the subsequent native producer commit; verify its
exact hosted SHA separately after push.
