# peer

> Build AI PR review agents with evaluation built in.

`peer` is an opinionated framework for building AI agents that review code changes — and a way to know your agent is actually good.

## Why this exists

Commercial AI PR reviewers (CodeRabbit, Greptile, Cursor review, Copilot Code Review, Codium) work for many teams. They don't work for every team — security constraints, codebase quirks, opinionated review styles, and unique team practices push organizations to build their own.

When teams build their own, they hit two problems:

1. **No framework exists.** Each team rebuilds the same plumbing — pulling diffs, gathering context, formatting comments, integrating with GitHub. Codium's PR-Agent went commercial; GitHub Agentic Workflows is generic; there's nothing opinionated and OSS for the PR-review-specific shape.

2. **No measurement.** Teams ship and hope. There's no obvious way to know whether the agent's reviews are catching real issues, or just generating noise.

`peer` exists to solve both. It's a framework for building PR review agents, with an evaluation harness built in that uses your repo's own historical reviews as the gold standard.

## Status

**Alpha (v0.0.1).** Public scaffolding, design rationale, and roadmap below. Real code lands over the coming weekends.

## Design philosophy

See [`docs/design.md`](docs/design.md) for the full rationale. Three principles:

1. **Eval-first.** Every framework feature is designed so you can measure whether it's actually helping. The eval harness is a first-class component, not an add-on.
2. **Historical reviews as gold standard.** Your repo already contains thousands of high-signal human reviews. `peer` mines those as the calibration set — your agent gets graded against the standard your team has already established.
3. **Opinionated, composable.** Sensible defaults out of the box; pluggable parts for teams that want to customize.

## Quickstart (planned API)

```python
from peer import Agent, eval

# Build a reviewer
agent = Agent(model="claude-opus-4-7")

# Review a single PR
review = agent.review(pr_url="https://github.com/owner/repo/pull/123")

# Evaluate the agent against your repo's review history
score = eval.against_history(
    agent=agent,
    repo="owner/repo",
    sample_size=50,
    date_range=("2023-01-01", "2023-12-31"),  # pre-AI-tool era for a clean human baseline
)
print(score)  # severity_match, coverage, false_positive_rate, comment_substance
```

## Roadmap

- **v0.1** — agent + GitHub integration + basic eval (severity match, coverage)
- **v0.2** — pluggable reviewer interface; multi-model support
- **v0.3** — side-by-side comparison with commercial reviewers (BYO API key)
- **v1.0** — production-ready, documented, example deployments

## Contributing

Contributions welcome once the v0.1 surface is stable. Until then, issues and design discussion via GitHub Issues.

## License

MIT.
