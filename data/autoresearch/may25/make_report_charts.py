"""Minimalist chart generation — v5.

Three charts. One point each. No whiskers, no per-run dots, no callouts,
no footnotes, no methodological text. The report body carries the caveats;
the charts are the visual.

  1. bug_catching_bars.png — 3 bars: per-PR recall across recipes
  2. pareto_2d.png        — detection_rate vs comments_per_pr scatter
  3. cost_vs_recall.png   — cost vs recall scatter
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

C_NARROWER = "#2c7a4b"
C_AGENTIC = "#4a7ca7"
C_BASELINE = "#bababa"
INK = "#222222"
INK_MUTED = "#777777"
GRID = "#eeeeee"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "axes.labelcolor": INK_MUTED,
        "axes.edgecolor": INK_MUTED,
        "axes.titlecolor": INK,
        "axes.labelsize": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = Path(__file__).resolve().parent / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)


def _load(name: str) -> dict:
    return json.loads((ROOT / "data" / "eval_runs" / name).read_text())


def _band_median(mr: dict, metric: str) -> float | None:
    band = mr.get("metric_bands", {}).get(metric) or {}
    return band.get("median")


def _per_pr_cost(mr: dict) -> float | None:
    """Median per-PR cost across runs."""
    per_run = []
    for r in mr["per_run"]:
        total, n = 0.0, 0
        for s in r["per_sample"]:
            c = ((s.get("review_summary") or {}).get("usage") or {}).get("total_cost_usd")
            if isinstance(c, (int, float)):
                total += float(c)
                n += 1
        if n > 0:
            per_run.append(total / 30.0)
    if not per_run:
        return None
    return sorted(per_run)[len(per_run) // 2]


agentic = _load("multirun_d269ac1d_1199de6.json")
narrower = _load("multirun_f7caeb70_1199de6.json")
cmp_ = json.loads((ROOT / "data" / "eval_runs" / "comparison_f7caeb70_1199de6.json").read_text())
baseline_med = {e["metric"]: e["baseline_median"] for e in cmp_["per_metric"]}


def add_title(fig, text: str) -> None:
    fig.text(0.02, 0.96, text, fontsize=14, fontweight="bold", color=INK, ha="left", va="top")


# ----------------------------------------------------------------------------
# Chart 1: per-PR recall, 3 bars
# ----------------------------------------------------------------------------


def chart_recall() -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.subplots_adjust(top=0.83, bottom=0.13, left=0.10, right=0.95)

    recipes = [
        ("narrower", _band_median(narrower, "mean_per_pr_recall"), C_NARROWER),
        ("agentic", _band_median(agentic, "mean_per_pr_recall"), C_AGENTIC),
        ("baseline", baseline_med.get("mean_per_pr_recall"), C_BASELINE),
    ]
    xs = list(range(len(recipes)))
    for x, (name, val, color) in zip(xs, recipes, strict=False):
        ax.bar(x, val, color=color, width=0.55, edgecolor="none")
        ax.text(x, val + 0.003, f"{val:.3f}", ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK)
    ax.set_xticks(xs)
    ax.set_xticklabels([r[0] for r in recipes], fontsize=11, color=INK)
    ax.set_ylabel("mean per-PR recall (median across N=3 runs)", color=INK_MUTED)
    ax.set_ylim(0, max(r[1] or 0 for r in recipes) * 1.25)
    ax.tick_params(left=False, bottom=False)

    add_title(fig, "Per-PR recall: narrower ≈ 2× agentic ≈ 40× bare baseline")
    out = CHART_DIR / "bug_catching_bars.png"
    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# ----------------------------------------------------------------------------
# Chart 2: 2D scatter — detection vs comments
# ----------------------------------------------------------------------------


def chart_pareto() -> Path:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    fig.subplots_adjust(top=0.83, bottom=0.14, left=0.12, right=0.95)

    points = [
        ("narrower",
         _band_median(narrower, "comments_per_pr"),
         _band_median(narrower, "detection_rate"),
         C_NARROWER),
        ("agentic",
         _band_median(agentic, "comments_per_pr"),
         _band_median(agentic, "detection_rate"),
         C_AGENTIC),
        ("baseline",
         baseline_med.get("comments_per_pr"),
         baseline_med.get("detection_rate"),
         C_BASELINE),
    ]
    for name, x, y, color in points:
        ax.scatter(x, y, s=260, color=color, edgecolor="white", linewidth=2, zorder=3)
        ax.annotate(
            name, xy=(x, y), xytext=(12, 8), textcoords="offset points",
            fontsize=12, fontweight="bold", color=color,
        )

    ax.set_xlabel("comments per PR (lower = quieter)", color=INK_MUTED)
    ax.set_ylabel("detection rate (higher = more bugs)", color=INK_MUTED)
    ax.tick_params(left=False, bottom=False)
    ax.grid(axis="both", linestyle="-", linewidth=0.8, color=GRID, alpha=0.7)

    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    ax.set_xlim(min(xs) - 0.3, max(xs) + 0.5)
    ax.set_ylim(0, max(ys) * 1.35)

    add_title(fig, "narrower catches more bugs; agentic is slightly quieter; baseline is dominated")
    out = CHART_DIR / "pareto_2d.png"
    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# ----------------------------------------------------------------------------
# Chart 3: cost vs recall
# ----------------------------------------------------------------------------


def chart_cost() -> Path:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    fig.subplots_adjust(top=0.83, bottom=0.14, left=0.12, right=0.95)

    points = [
        ("narrower",
         _per_pr_cost(narrower),
         _band_median(narrower, "mean_per_pr_recall"),
         C_NARROWER),
        ("agentic",
         _per_pr_cost(agentic),
         _band_median(agentic, "mean_per_pr_recall"),
         C_AGENTIC),
    ]
    for name, x, y, color in points:
        ax.scatter(x, y, s=280, color=color, edgecolor="white", linewidth=2, zorder=3)
        ax.annotate(
            f"{name}\n${x:.2f} / PR · recall {y:.2f}",
            xy=(x, y), xytext=(14, 10), textcoords="offset points",
            fontsize=11, fontweight="bold", color=color,
        )

    ax.set_xlabel("cost per PR (USD)", color=INK_MUTED)
    ax.set_ylabel("mean per-PR recall", color=INK_MUTED)
    ax.tick_params(left=False, bottom=False)
    ax.grid(axis="both", linestyle="-", linewidth=0.8, color=GRID, alpha=0.7)

    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    ax.set_xlim(min(xs) - 0.015, max(xs) + 0.03)
    ax.set_ylim(0, max(ys) * 1.4)

    add_title(fig, "Same cost, half the recall: agentic tool-loop doesn't pay for itself")
    out = CHART_DIR / "cost_vs_recall.png"
    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    # Remove the obsolete all_metrics_split chart
    obsolete = CHART_DIR / "all_metrics_split.png"
    if obsolete.exists():
        obsolete.unlink()
        print(f"removed {obsolete.relative_to(ROOT)}")
    for path in (chart_recall(), chart_pareto(), chart_cost()):
        print(f"wrote {path.relative_to(ROOT)}")
