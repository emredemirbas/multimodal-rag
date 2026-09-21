# Sprint 0 cost model

This is a budgeting model, not a vendor quote. Unit rates are explicit inputs so
they can be replaced after provider selection and procurement. The example uses:

| Input | Planning assumption |
|---|---:|
| Transcript tokens per video hour | 15,000 |
| Selected/described frames per hour | 120 |
| ASR per audio minute | $0.006 |
| Embeddings per million tokens | $0.02 |
| Visual description per selected frame | $0.0005 |
| Derived storage per hour | 25 MB |
| Object storage per GB-month | $0.023 |
| Contingency | 20% |

Using these illustrative assumptions:

| Path | One hour | Ten hours | 1h + 20% | 10h + 20% |
|---|---:|---:|---:|---:|
| Uploaded transcript plus visual evidence | $0.0609 | $0.6086 | $0.0730 | $0.7303 |
| Authorized media including ASR | $0.4209 | $4.2086 | $0.5050 | $5.0503 |

The estimate excludes user chat, reranking, retries, taxes, egress, idle
infrastructure, and engineering labor. Those costs depend on usage rather than
processed duration and must be measured separately.

Recalculate with current provider rates:

```bash
python3 scripts/estimate_cost.py --hours 1
python3 scripts/estimate_cost.py --hours 10
```

The first production-backed spike must record actual transcript duration, frame
count, tokens, provider calls, latency, and attributable cost alongside this
estimate.
