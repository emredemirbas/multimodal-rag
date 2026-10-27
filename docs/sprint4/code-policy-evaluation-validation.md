# Paired code/terminal policy diagnostic verification

Date: 2026-10-27. Operator-only measurement follow-up; no policy/default promotion,
schema migration, application endpoint or representative quality approval.

## Software evidence

- **37 new backend cases** cover paired policy/engine/language/input binding,
  one validated label snapshot under caller mutation, combined budget preflight,
  decoded shared-pixel conflicts and alternate PNG compression, coverage losses
  and gains, null shared-sample denominators, safe CLI ordering/output, fixed
  authored schedules/literal identifiers/rendering, isolation and temporary-file
  cleanup on failure. With the existing visual-evaluation cases: **86 passed in
  0.60s**. The legacy evaluator's output and normalization remain unchanged.
- Final full regression: **891 passed, zero skipped, 179.23s**, including actual
  worker process-loss tests (`TEST_REAL_WORKER=1`) against fresh random-port
  PG/pgvector, Redis and MinIO containers with test-only credentials/tmpfs. Only
  recorded new container IDs were removed. One upstream Starlette/httpx TestClient
  warning remains unsuppressed. No timeout, assertion or isolation limit weakened.
- An earlier renderer-test assertion matched `text=` inside the word `drawtext=`
  (five failures); correcting that test to recognize the actual inline option
  boundary fixed the false positive, without changing native rendering. An
  intermediate full run passed 890 cases before the final snapshot regression
  case was added; the final 891-case run above supersedes it.
- No frontend source changed or new local frontend run claimed. Existing
  tenant/project/actor, evidence-generation, retry, deletion and native boundary
  coverage remains in the full backend suite. These stateless tools have no
  project-owned records or application credentials; no migration is needed.

## Actual isolated native evidence

Built the minimal native image separately and executed the five-case suite in a
new non-root/read-only/network-none container: 192 MiB tmpfs, 1 GiB RAM/no extra
swap, two CPUs, 32 PIDs, no capabilities/new privileges/core dumps, no host mounts
or app credentials. Existing child/per-call limits are unchanged. All five cases
complete with valid content-free JSON and **zero application records created**.
Poor coverage/OCR is reported, not treated as execution failure or hidden.

The standalone authorized-reference paired CLI also passes on the terminal probe,
with verified MP4 bytes, no raw text/code/path output or stderr. The unchanged
private uniform HTTP/native check passes with four candidates/two retained frames
at `[0,10000]`, actual OCR/profile pinning and inherited socket-denial checks.

All clips are originally authored, 20 seconds, 960x540; fixed monospace grayscale
text, lossless H.264. Source rate is 2fps except the 10fps sub-second probe.
Independent synthetic text/schedules precede recognition; not human-reviewed
recordings. Both policies use the same FFmpeg `5.1.9-0+deb12u1`, Tesseract `5.3.0`
and English/Turkish data hashes already present in the native identity. No model
download, paid service, network fallback, owner data or external media is used.

| Authored case | Uniform retained PTS (ms) | Change retained PTS (ms) | Labeled interval coverage, uniform / change | Important finding |
|---|---|---|---|---|
| `terminal_error` | 0 | 0, 3000, 4000, 7000, 13000, 19000 | 1/3 / 3/3 | Change captures the 3–4s error and its return; uniform misses both intervals |
| `single_digit` | 0, 5000 | 0, 7000, 13000, 19000 | 2/3 / 2/3 | Change **loses** the 5–6s one-digit edit that uniform captures, while gaining the return interval |
| `cursor_motion` | 0, 5000 | Every 1000ms from 0 through 19000 (20 frames) | 1/1 / 1/1 | Cursor-only changes consume all 20 retained slots without additional labeled-text coverage |
| `subsecond_view` | 0 | 0, 7000, 13000, 19000 | 1/3 / 2/3 | **Both miss** the 3.2–3.6s view; change only gains its later return interval |
| `turkish_code` | 0 | 0, 7000, 13000, 19000 | 1/1 / 1/1 | No extra interval coverage; mixed Turkish/technical OCR errors remain |

All-frame micro-aggregates have different sampling weights. They are **not** an
overall policy ranking; all counts and both full reports remain in the JSON:

| Case | Reference words, uniform / change | WER, uniform / change | Normalized CER, uniform / change | Literal CER, uniform / change |
|---|---:|---:|---:|---:|
| `terminal_error` | 7 / 44 | 0 / 0 | 0 / 0 | 0.033333 / 0.039648 |
| `single_digit` | 12 / 24 | 0.166667 / 0.166667 | 0.038462 / 0.038462 | 0.145161 / 0.145161 |
| `cursor_motion` | 14 / 140 | 0 / 0 | 0 / 0 | 0.029412 / 0.029412 |
| `subsecond_view` | 2 / 8 | 0 / 0 | 0 / 0 | 0.071429 / 0.071429 |
| `turkish_code` | 9 / 36 | 0.222222 / 0.222222 | 0.014925 / 0.014925 | 0.037975 / 0.037975 |

Listed identifier recall is 1 on every policy's **retained labeled samples**.
That does not establish syntax/indentation/compilation correctness or recovery of
the missing digit/sub-second intervals. At shared identical-image PTS (`[0]`, or
`[0,5000]` for cursor motion), paired OCR rates are identical under both policies;
that comparison has matching sample weights. Literal errors remain visible even
when normalized WER/CER is zero. No new quality threshold or automatic winner.

Exact native profiles used:

- English uniform: `local-visual-v1:5ab2f89ea6b52c676eed781735e19fefbf80e24ffcac313e5d1a5615b044fc89`
- English change: `local-visual-v2:6be8762315e8ced16cbb4a032662549baceb6435c24207de82f95285d263d5b3`
- English+Turkish uniform: `local-visual-v1:8670c9784b7741d392431ef1d7c87ba22cc73fbae3119b6025e05731cc17bb8f`
- English+Turkish change: `local-visual-v2:c5ff0894a64c49684f1bde742a62c170f669dbddaf40ca6e02c21bb8d1d0cacd`

| Case | Input bytes | Input SHA-256 | Reference SHA-256 |
|---|---:|---|---|
| `terminal_error` | 169332 | `5c43ed407c0bbb30b0efaff7aa70eeae6cc9bbeaa65e0be4a0c01d83bbc5f7a1` | `6375fa9cbd1ea02687a448d9c992d4e641b35617754e8eeba156b346e643e16f` |
| `single_digit` | 219748 | `4190ca00a0aa85d5e832be0ebeb4e5f1999eaf6b1b387b80a42ceba800f62239` | `519640f5c7ebfbc368c3a81df90e70698dd4118802d143ce1d65cbcf1a3ef9b9` |
| `cursor_motion` | 167679 | `a5215df76436b2971e4fd5916adee42b82f6ce4bd96829c0a82816f31f0d9bcf` | `89e91289b192cf7903a32934b2bb58911262eaa6e891ec03fdc91cda212cece8` |
| `subsecond_view` | 481298 | `39af3c098fb0fdce583ea0aaa1d36d073105aad7042dd5062c71bebacd18af93` | `77cdfcd1b6423d8d0b4a2c0bce7b938aa66ca93e6a40e8d3122b8b7eebe1bcc3` |
| `turkish_code` | 252309 | `1a1dbc335152d2f0d99b5f3aab169dac63d37365865f3e911f482ad5bea7b769` | `25fdf93ab1b8e3447e2a5150344f46889573f4c2af96e8d0ac2a024c524a4f36` |

## Scope and hosted status

CI now executes the same authored suite as a native integrity/execution check,
not a metric-quality gate. No schema, provider, policy/profile parameter, resource
budget, format, retention, owner `.env`, running service, upload flag or default
changed. Uniform stays default. This tiny favorable/unfavorable authored set does
not establish representative IDE/terminal, semantic-scene or audiovisual quality,
whole-clip performance, Sprint 4 completion or Alpha 2.

The separately verified **previous** hosted baseline is
`5cf6da8950589ac82bb6888b4bf9926d56eb5ecd`, all four jobs successful in
[run 40573984408](https://github.com/emredemirbas/multimodal-rag/actions/runs/40573984408).
That result does not certify this subsequent paired-diagnostic commit; verify its
exact hosted SHA after push. See `code-policy-evaluation-guide.md` to reproduce.
