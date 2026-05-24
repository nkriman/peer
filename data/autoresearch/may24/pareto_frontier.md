# Pareto frontier — architecture sweep

Sweep over recipe architecture (model, context depth, strategy).
All runs go through the `claude` CLI; real API spend is $0 — cost values
are Claude Code's *would-be* SDK billing.

- total rows in TSV: 19
- successful rows: 19
- Pareto frontier size: 7

## Pareto-optimal recipes (DR ↑, comments ↓, cost ↓)

| DR | comments | cost | description |
|---:|---:|---:|---|
| 0.0980 | 29 | $0.8328 | arch[narrower context: ctx=10K, call_sites=2] |
| 0.0784 | 32 | $0.4350 | iter-2: replace 'false positives > missed issues' guardrail with active encouragement to f |
| 0.0784 | 31 | $0.7495 | arch[baseline: sonnet, ctx=30K, call_sites=5, no strategy] |
| 0.0588 | 22 | $0.8109 | sweep[T=0.0,sev_floor=None,max_comments=None] |
| 0.0392 | 22 | $0.0000 | arch[strategy=draft_critique (CLI inner + CLI critique)] |
| 0.0196 | 7 | $0.2379 | arch[model=haiku] |
| 0.0000 | 0 | $0.0000 | arch[strategy=self_filter (CLI inner)] |

## All sweep runs (sorted by detection_rate ↓)

| DR | comments | cost | on frontier? | description |
|---:|---:|---:|:---:|---|
| 0.0980 | 29 | $0.8328 | ★ | arch[narrower context: ctx=10K, call_sites=2] |
| 0.0784 | 31 | $0.7495 | ★ | arch[baseline: sonnet, ctx=30K, call_sites=5, no strategy] |
| 0.0392 | 29 | $0.7721 |  | arch[wider context: ctx=60K, call_sites=15] |
| 0.0392 | 30 | $1.8236 |  | arch[model=opus] |
| 0.0392 | 22 | $0.0000 | ★ | arch[strategy=draft_critique (CLI inner + CLI critique)] |
| 0.0196 | 7 | $0.2379 | ★ | arch[model=haiku] |
| 0.0000 | 0 | $0.0000 | ★ | arch[strategy=self_filter (CLI inner)] |