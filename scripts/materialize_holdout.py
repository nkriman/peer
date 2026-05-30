"""Materialize the fresh revert-based holdout (benchmark-the-field Phase 1, peer-4z5).

Network job, ~no Claude quota: mines revert-linked buggy PRs across several
high-velocity repos merged after the contamination cutoff, then writes them as
GoldSamples to dataset/reference/benchmark_holdout.jsonl.

Run: uv run python scripts/materialize_holdout.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from peer.dataset.holdout import mine_holdout
from peer.dataset.storage import JSONLStorage

# High-velocity repos that use GitHub's "Revert ... (#N)" convention. Revert-only
# mining under-harvests, so cast a wide net; the miner keeps only revert PRs that
# link back to a specific buggy PR number AND whose buggy PR merged after cutoff.
REPOS = [
    "microsoft/vscode",
    "facebook/react",
    "kubernetes/kubernetes",
    "pytorch/pytorch",
    "vercel/next.js",
    "elastic/elasticsearch",
    "grafana/grafana",
    "rust-lang/rust",
    "golang/go",
    "home-assistant/core",
]

CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)
OUT = Path("dataset/reference/benchmark_holdout.jsonl")


def main() -> None:
    samples = mine_holdout(REPOS, cutoff=CUTOFF, per_repo_limit=200)
    storage = JSONLStorage(OUT)
    for s in samples:
        storage.add(s)
    safe = sum(1 for s in samples if s.metadata.contamination_safe is True)
    print(f"HOLDOUT_TOTAL={len(samples)}")
    print(f"HOLDOUT_CONTAMINATION_SAFE={safe}")
    print(f"HOLDOUT_OUT={OUT}")


if __name__ == "__main__":
    main()
