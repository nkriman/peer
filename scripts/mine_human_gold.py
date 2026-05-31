"""Mine the human-review gold benchmark from a mature repo (peer-e94).

Selected repo: kubernetes/kubernetes (peer-7q1) — ~50% of merged PRs carry
dense, substantive, line-anchored human inline review.

Two phases so the expensive step is separable + resumable:
  --select : (cheap, paced gh, no LLM) scan merged PRs, keep DENSE ones
             (>= MIN_DENSE human inline comments), write the candidate list.
  --curate : (haiku/sonnet via subscription) run each candidate through the
             existing curation pipeline, keep PRs that yield >= 1 DEFECT-class
             gold, write benchmark_humangold.jsonl + manifest.

Reuses peer's pipeline wholesale (no new curation logic): GitHubInlineCommentSource
(orchestration filter live) -> LLMCommentClassifier(model=sonnet via
PEER_USE_CLAUDE_CODE=1) -> Curator.add(auto_accept=True). Taxonomy defect
categories define the headline; style-nit/discussion are dropped from the lead.

Run (fresh shell, subscription):
  uv run python scripts/mine_human_gold.py --select
  PEER_USE_CLAUDE_CODE=1 uv run python scripts/mine_human_gold.py --curate
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from peer.dataset.classifier import LLMCommentClassifier
from peer.dataset.curation import Curator
from peer.dataset.storage import JSONLStorage
from peer.dataset.taxonomy import DefaultTaxonomy

REPO = "kubernetes/kubernetes"
SCAN = 150  # merged PRs to scan in --select
MIN_DENSE = 2  # human inline comments to qualify a PR as densely reviewed
TARGET_PRS = 50  # stop selecting once we have this many dense candidates
API_SLEEP = 1.5
BACKOFF = 8.0
MAX_ATTEMPTS = 4

CANDIDATES = Path("data/probes/humangold_candidates.json")
OUT = Path("dataset/reference/benchmark_humangold.jsonl")
MANIFEST = Path("dataset/reference/benchmark_humangold.manifest.json")
CACHE = Path("/tmp/peer_classifier_cache/humangold.jsonl")

# Headline gold = real defects; style-nit/discussion stay out of the lead number.
DEFECT_CATEGORIES = {c.name for c in DefaultTaxonomy.categories if c.is_defect}


def _gh(args: list[str]):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False, timeout=120
        )
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                return None
        if "rate limit" in (proc.stderr or "").lower():
            time.sleep(BACKOFF * attempt)
            continue
        return None
    return None


def _human_inline_count(repo: str, number: int) -> int:
    data = _gh(["api", f"repos/{repo}/pulls/{number}/comments", "--paginate"])
    time.sleep(API_SLEEP)
    if not isinstance(data, list):
        return 0
    n = 0
    for c in data:
        if isinstance(c, dict):
            login = (c.get("user") or {}).get("login", "")
            if login and not login.endswith("[bot]"):
                n += 1
    return n


def select() -> None:
    print(f"Selecting dense merged PRs from {REPO} (scan {SCAN}, target {TARGET_PRS})")
    nums = _gh(
        [
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "merged",
            "--limit",
            str(SCAN),
            "--json",
            "number",
        ]
    )
    time.sleep(API_SLEEP)
    if not isinstance(nums, list):
        print("NO DATA")
        sys.exit(1)
    numbers = [d["number"] for d in nums if "number" in d]
    dense = []
    for i, n in enumerate(numbers, 1):
        c = _human_inline_count(REPO, n)
        if c >= MIN_DENSE:
            dense.append({"repo": REPO, "number": n, "human_inline": c})
            print(f"  [{len(dense)}] PR #{n}: {c} human inline")
        if len(dense) >= TARGET_PRS:
            break
        if i % 20 == 0:
            print(f"  ...scanned {i}/{len(numbers)} ({len(dense)} dense so far)")
    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES.write_text(json.dumps(dense, indent=2))
    print(f"\nwrote {len(dense)} dense candidates -> {CANDIDATES}")


def curate() -> None:
    if not CANDIDATES.exists():
        print(f"no candidates at {CANDIDATES}; run --select first")
        sys.exit(1)
    cands = json.loads(CANDIDATES.read_text())
    print(f"Curating {len(cands)} candidate PRs from {REPO}")
    classifier = LLMCommentClassifier(model="sonnet", cache_path=CACHE)
    if OUT.exists():
        OUT.unlink()
    storage = JSONLStorage(OUT)
    curator = Curator(classifier=classifier, storage=None)  # preview, then filter+store

    kept = 0
    total_defects = 0
    for i, c in enumerate(cands, 1):
        url = f"https://github.com/{c['repo']}/pull/{c['number']}"
        try:
            proposed = curator.preview(url)
            sample = proposed.proposed
            defect_golds = [d for d in sample.gold_defects if d.category in DEFECT_CATEGORIES]
            if not defect_golds:
                print(f"[{i}/{len(cands)}] #{c['number']}: 0 defect-gold (skip)")
                continue
            # Keep only defect-class gold in the stored sample.
            sample = sample.model_copy(update={"gold_defects": defect_golds})
            storage.add(sample)
            kept += 1
            total_defects += len(defect_golds)
            cats = sorted({d.category for d in defect_golds})
            print(f"[{i}/{len(cands)}] #{c['number']}: {len(defect_golds)} defect-gold {cats}")
        except Exception as e:
            print(f"[{i}/{len(cands)}] #{c['number']}: ERROR {e}")

    manifest = {
        "repo": REPO,
        "source": "human-review-inline",
        "candidates": len(cands),
        "prs_with_defect_gold": kept,
        "total_defect_gold": total_defects,
        "defect_categories": sorted(DEFECT_CATEGORIES),
        "min_dense_inline": MIN_DENSE,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print("\n========== HUMAN-GOLD SUMMARY ==========")
    print(f"PRs kept (>=1 defect gold): {kept}/{len(cands)}")
    print(f"total defect gold: {total_defects}")
    print(f"dataset: {OUT}\nmanifest: {MANIFEST}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true", help="scan + pick dense PRs (no LLM)")
    ap.add_argument("--curate", action="store_true", help="classify + write gold (needs model)")
    args = ap.parse_args()
    if args.select:
        select()
    elif args.curate:
        curate()
    else:
        ap.error("pass --select or --curate")


if __name__ == "__main__":
    main()
