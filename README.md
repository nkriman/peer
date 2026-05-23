# peer

> peer — build AI PR review agents with evaluation built in.

`peer` is an opinionated framework for building AI agents that review code changes — and a way to know your agent is actually good. It ships an `Agent` that reviews one PR end-to-end, an `EvalRunner` that grades it against a curated dataset of real PR defects, and the dataset-curation pipeline that builds the dataset in the first place.

It's a framework, not a turnkey reviewer. The defaults work out of the box on a generic OSS Python repo; the value lands once you swap in your own classifier, your own taxonomy of "what counts as a defect", and your own gold dataset for your repo.

## Quickstart

Three commands take you from install to a real eval run on the bundled reference dataset.

```bash
# 1. Install (local dev for now; PyPI release will land with v0.1.0)
pip install -e .

# 2. Review a single PR with the default Agent
peer review https://github.com/owner/repo/pull/N

# 3. Run the default eval on the shipped reference dataset
peer eval --dataset dataset/reference/django_pydantic_v1.jsonl
```

`peer eval` writes a JSON `EvalReport` to `data/eval_runs/<run_id>.json` and prints a CLI summary. Pass `--baseline <prior_report.json>` for an A/B diff.

## Customizing for your repo

Everything in `peer` is a Protocol with a default implementation. You override by constructing the eval surface with your own pieces — no subclassing, no config files.

```python
from peer import Agent, EvalRunner, DefectRecall, NoveltyRate
from peer.dataset import JSONLStorage

# Use your own dataset
samples = JSONLStorage("my_team/dataset.jsonl").load_all()

# Use your own metric mix (drop SeverityCalibration, add a custom one)
class TeamCriticalRecall:
    name = "team_critical_recall"
    def compute(self, results, dataset):
        # returns a MetricResult; see peer.eval.EvalMetric
        ...

runner = EvalRunner(
    reviewer=Agent(model="claude-opus-4-7"),
    dataset=samples,
    metrics=[DefectRecall(), NoveltyRate(), TeamCriticalRecall()],
)
report = runner.run()
print(report.summary)
```

The same constructor-injection pattern applies to `CommentClassifier`, `Taxonomy`, `EnrichmentStep`, `GoldSampleStorage`, `EvalReport`, and `RawSampleSource`. See [`docs/framework_overview.md`](docs/framework_overview.md) for the full extension-point surface.

## Requirements

- Python ≥ 3.10
- `gh` CLI installed and authenticated (`gh auth status` should pass) — used for fetching PR diffs and inline comments
- `ANTHROPIC_API_KEY` in the environment — used by the default `Reviewer` and `LLMCommentClassifier`

The dataset-curation classifier uses Haiku 4.5 (~$0.001 per raw comment classified). The default reviewer uses Sonnet 4.6.

## Status

**v0.1, local-development.** The eval surface (`peer eval`, `peer dataset`) just shipped via the `eval-v01` change. The reference dataset at `dataset/reference/django_pydantic_v1.jsonl` is ~30 samples drawn from Django + Pydantic. The SOTA-comparison benchmark (`benchmark-v01`) — where peer-built reviewers go up against commercial baselines like CodeRabbit, Greptile, Cursor review — is forthcoming.

Public installation via PyPI lands once v0.1.0 is tagged.

## What `peer` is not

- Not a general-purpose agent framework. Use Pydantic AI.
- Not a multi-tool PR helper (no describe, improve, ask, changelog). Use Qodo's PR-Agent.
- Not a reviewer; it's the framework you build your reviewer inside. Out of the box you get a working baseline; the value is in the iteration loop.
- Not a hosted service. Library + CLI only.

## Why this exists

Commercial AI PR reviewers (CodeRabbit, Greptile, Cursor review, Copilot Code Review, Codium) work for many teams. They don't work for every team — security constraints, codebase quirks, opinionated review styles, and unique team practices push organizations to build their own.

When teams build their own, they hit two problems:

1. **No framework exists.** Each team rebuilds the same plumbing — pulling diffs, gathering context, formatting comments, integrating with GitHub.
2. **No measurement.** Teams ship and hope. There's no obvious way to know whether the agent's reviews are catching real issues or just generating noise.

`peer` exists to solve both. It's a framework for building PR review agents, with an evaluation harness built in that uses your team's curated historical reviews as the gold standard.

## Design philosophy

See [`docs/design.md`](docs/design.md) for the long version and [`docs/framework_overview.md`](docs/framework_overview.md) for the architectural deep-dive. Three principles:

1. **Eval-first.** Every framework feature is designed so you can measure whether it's actually helping. The eval harness is a first-class component, not an add-on.
2. **Curated gold, not raw comments.** Your repo's review history is the calibration signal, but raw inline comments need to be classified and filtered before they're useful as ground truth. `peer` ships the pipeline that does this.
3. **Opinionated, composable.** Sensible defaults out of the box; eight Protocols you can swap independently for teams that want to customize.

## Docs

- [`docs/framework_overview.md`](docs/framework_overview.md) — architectural deep-dive: the eval loop, the eight Protocols, the two subpackages, the default taxonomy, the default metrics
- [`docs/dataset_curation_guide.md`](docs/dataset_curation_guide.md) — methodology for curating your own gold dataset
- [`docs/design.md`](docs/design.md) — design rationale
- [`docs/scope_research.md`](docs/scope_research.md) — what's in / out of scope, with research backing
- [`docs/codebase_understanding_research.md`](docs/codebase_understanding_research.md) — survey of how leading tools handle codebase context
- [`docs/oss_leverage_research.md`](docs/oss_leverage_research.md) — what OSS pieces `peer` builds on vs reinvents

## Roadmap

- **v0.1 (current)** — agent + GitHub integration + eval framework + dataset curation pipeline + reference dataset
- **v0.2** — stronger default codebase context (tree-sitter symbol extraction, call-site lookup, test-file inclusion) per `codebase_understanding_research.md`
- **`benchmark-v01`** — SOTA-comparison benchmark against commercial reviewers (CodeRabbit, Greptile, Cursor review) using BYO-API-key adapters
- **v1.0** — production-ready, documented, example deployments

## Contributing

Contributions welcome once the v0.1 surface is stable. Until then, issues and design discussion via GitHub Issues.

## License

MIT.
