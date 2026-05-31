"""Small-batch gold-YIELD check for the in-the-wild track (peer-5u5).

The probe (peer-b8t) showed 40% of bot-reviewed PRs have a human-comment signal.
But "has a human comment" overcounts "has a real defect": a comment may be a
nit, a question, or praise. This script measures the POST-CLASSIFIER yield —
how many PRs actually produce >=1 GoldDefect once human review comments run
through peer's existing curation pipeline (source -> LLM classifier -> taxonomy
defect-filter). That is the real gold rate Track 2 will get.

Reuses the existing machinery wholesale (no new curation logic):
  GitHubInlineCommentSource (bot-filters CodeRabbit/Greptile/Qodo) ->
  LLMCommentClassifier (haiku, on-disk cached) -> Curator.add(auto_accept=True).

Only INLINE comments (path+line) can become anchored GoldDefects, so we select
candidate PRs by human_review_comments > 0 from the probe JSON, prioritising the
2+-tool-overlap slice and capping per-repo to avoid same-repo clustering.

Costs haiku quota: ~1 classifier call per human comment (cached on re-run).
Run: uv run python scripts/yield_check_inthewild.py

GO/SCALE gate: if >= ~50% of sampled PRs yield >=1 gold defect AND the defects
look real on spot-check, scale to a 30-50 PR benchmark_inthewild.jsonl. Lower ->
revisit selection (target higher-review repos) before scaling.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from peer.dataset.classifier import LLMCommentClassifier
from peer.dataset.curation import Curator
from peer.dataset.storage import JSONLStorage

PROBE = Path("data/probes/inthewild_gold_probe_2026-05-31.json")
OUT = Path("/tmp/inthewild_yield.jsonl")
CACHE = Path("/tmp/peer_classifier_cache")
MAX_PRS = 12
MAX_PER_REPO = 2


def _select_candidates() -> list[dict]:
    """Pick PRs with >=1 human INLINE comment (only those can yield anchored
    gold), overlap-first, capped per repo."""
    data = json.loads(PROBE.read_text())
    cands: list[dict] = []
    for tool, probes in data.items():
        for p in probes:
            if p.get("human_review_comments", 0) > 0:
                cands.append(
                    {
                        "tool": tool,
                        "repo": p["repo"],
                        "number": p["number"],
                        "url": p["url"],
                        "human_review": p["human_review_comments"],
                        "overlap": bool(p.get("other_bots")),
                    }
                )
    # overlap first, then more human review comments.
    cands.sort(key=lambda c: (not c["overlap"], -c["human_review"]))
    selected: list[dict] = []
    per_repo: dict[str, int] = defaultdict(int)
    for c in cands:
        if per_repo[c["repo"]] >= MAX_PER_REPO:
            continue
        per_repo[c["repo"]] += 1
        selected.append(c)
        if len(selected) >= MAX_PRS:
            break
    return selected


def main() -> None:
    candidates = _select_candidates()
    print(f"selected {len(candidates)} candidate PRs (overlap-first, <= {MAX_PER_REPO}/repo):")
    for c in candidates:
        print(f"  {c['repo']}#{c['number']} review={c['human_review']} overlap={c['overlap']}")

    if OUT.exists():
        OUT.unlink()
    # Route through the claude-code subscription (PEER_USE_CLAUDE_CODE=1) with
    # sonnet — $0 marginal cost on the Max plan, stronger model than haiku.
    classifier = LLMCommentClassifier(model="sonnet", cache_path=CACHE / "classifications.jsonl")
    storage = JSONLStorage(OUT)
    curator = Curator(classifier=classifier, storage=storage)

    rows = []
    for i, c in enumerate(candidates, 1):
        url = c["url"]
        try:
            gs = curator.add(url, auto_accept=True)
            n_gold = len(gs.gold_defects)
            n_raw = gs.metadata.raw_comment_count
            cats = sorted({d.category for d in gs.gold_defects})
            print(
                f"[{i}/{len(candidates)}] {c['repo']}#{c['number']}: raw={n_raw} gold={n_gold} {cats}"
            )
            rows.append({**c, "raw": n_raw, "gold": n_gold, "categories": cats})
        except Exception as e:
            print(f"[{i}/{len(candidates)}] {c['repo']}#{c['number']}: ERROR {e}")
            rows.append({**c, "raw": None, "gold": None, "error": str(e)})

    print("\n========== YIELD SUMMARY ==========")
    ok = [r for r in rows if r.get("gold") is not None]
    n = len(ok)
    with_gold = sum(1 for r in ok if r["gold"] > 0)
    total_defects = sum(r["gold"] for r in ok)
    if n:
        pct = 100 * with_gold / n
        print(f"PRs processed: {n}")
        print(f"PRs with >=1 gold defect: {with_gold} ({pct:.0f}%)")
        print(f"total gold defects mined: {total_defects}")
        gate = "GO / SCALE to 30-50" if pct >= 50 else "REVISIT selection before scaling"
        print(f"GATE (>=50% yield): {gate}")
    print(f"\ngold samples: {OUT}")


if __name__ == "__main__":
    main()
