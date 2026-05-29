"""Recipe-vs-baseline comparison (cross-run-v01).

`compare_to_baseline` takes two MultiRunReports and classifies each
metric's delta as `above_noise` / `in_noise` / `below_noise` given a
noise_floor threshold OR a per-metric bootstrap confidence interval.

Polarity: metrics in `LOWER_IS_BETTER` (cpp, cost_usd) are treated as
wins when the recipe is *below* baseline by more than the noise gate.
The raw `delta = recipe - baseline` is preserved verbatim in the entry
so reports show the literal direction; only the verdict honors polarity.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .cross_run import MultiRunReport

Verdict = Literal["above_noise", "in_noise", "below_noise"]

# Single source of truth — frontier.py imports this. A regression on
# these metrics is a positive delta; a win is a negative one.
LOWER_IS_BETTER: frozenset[str] = frozenset({"comments_per_pr", "cost_usd"})


def _directional_delta(metric: str, raw_delta: float) -> float:
    """Sign so that POSITIVE always means 'better than baseline'."""
    return -raw_delta if metric in LOWER_IS_BETTER else raw_delta


class ComparisonEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    recipe_median: float | None
    baseline_median: float | None
    delta: float | None  # raw delta = recipe_median - baseline_median
    verdict: Verdict | None
    # Optional bootstrap-CI fields. Populated by compare_to_baseline_ci.
    ci_lower: float | None = None
    ci_upper: float | None = None
    ci_method: str | None = None  # e.g. "bootstrap_percentile_95" or "bca_paired_95"
    permutation_pvalue: float | None = None  # populated by BCa+permutation gate


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noise_floor: float
    n_runs_recipe: int
    n_runs_baseline: int
    per_metric: list[ComparisonEntry] = Field(default_factory=list)


def _classify_by_floor(metric: str, raw_delta: float, noise_floor: float) -> Verdict:
    d = _directional_delta(metric, raw_delta)
    if d > noise_floor:
        return "above_noise"
    if d < -noise_floor:
        return "below_noise"
    return "in_noise"


def compare_to_baseline(
    recipe_report: MultiRunReport,
    baseline_report: MultiRunReport,
    noise_floor: float = 0.06,
) -> ComparisonReport:
    """Classify recipe vs baseline per-metric against a fixed noise floor.

    `noise_floor` default of 0.06 matches the reviewer-side run-to-run
    variance we measured on the hard subset (see
    `data/autoresearch/may24/noise_floor_finding.md`). Real corpora
    should calibrate their own — or use `compare_to_baseline_ci` for a
    per-metric bootstrap-CI gate instead of a single hand-picked number.
    """
    metric_names: set[str] = set()
    metric_names.update(recipe_report.metric_bands.keys())
    metric_names.update(baseline_report.metric_bands.keys())

    entries: list[ComparisonEntry] = []
    for name in sorted(metric_names):
        r_band = recipe_report.metric_bands.get(name)
        b_band = baseline_report.metric_bands.get(name)
        r_med = r_band.median if r_band else None
        b_med = b_band.median if b_band else None
        if r_med is None or b_med is None:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med,
                    baseline_median=b_med,
                    delta=None,
                    verdict=None,
                )
            )
            continue
        delta = r_med - b_med
        entries.append(
            ComparisonEntry(
                metric=name,
                recipe_median=r_med,
                baseline_median=b_med,
                delta=delta,
                verdict=_classify_by_floor(name, delta, noise_floor),
            )
        )

    return ComparisonReport(
        noise_floor=noise_floor,
        n_runs_recipe=recipe_report.n_runs,
        n_runs_baseline=baseline_report.n_runs,
        per_metric=entries,
    )


# ---------------------------------------------------------------------------
# Bootstrap-CI verdict gate (replacement for the 0.06 hand-cutoff)
# ---------------------------------------------------------------------------


def _per_run_values(report: MultiRunReport, metric: str) -> list[float]:
    out: list[float] = []
    for r in report.per_run:
        v = (r.summary.metric_values or {}).get(metric)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _bootstrap_delta_ci(
    recipe_values: list[float],
    baseline_values: list[float],
    n_resamples: int,
    confidence: float,
    rng: random.Random,
) -> tuple[float, float] | None:
    """Percentile bootstrap CI for (median(recipe) - median(baseline)).

    Returns None if either sample is empty.
    """
    if not recipe_values or not baseline_values:
        return None
    n_r = len(recipe_values)
    n_b = len(baseline_values)
    deltas: list[float] = []
    for _ in range(n_resamples):
        r_sample = [recipe_values[rng.randrange(n_r)] for _ in range(n_r)]
        b_sample = [baseline_values[rng.randrange(n_b)] for _ in range(n_b)]
        deltas.append(statistics.median(r_sample) - statistics.median(b_sample))
    deltas.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(alpha * n_resamples))
    hi_idx = min(n_resamples - 1, int((1.0 - alpha) * n_resamples) - 1)
    return deltas[lo_idx], deltas[hi_idx]


def _normal_cdf(x: float) -> float:
    """Standard-normal CDF via erf (no scipy dep)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Beasley-Springer-Moro). Sufficient
    precision for bootstrap CI alpha levels (no scipy dep)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"_normal_ppf domain is (0, 1); got {p}")
    # Acklam 2003 approximation; max abs error ~1e-9 over (0, 1).
    a = [
        -3.969683028665376e1,
        2.209460984245205e2,
        -2.759285104469687e2,
        1.383577518672690e2,
        -3.066479806614716e1,
        2.506628277459239e0,
    ]
    b = [
        -5.447609879822406e1,
        1.615858368580409e2,
        -1.556989798598866e2,
        6.680131188771972e1,
        -1.328068155288572e1,
    ]
    c = [
        -7.784894002430293e-3,
        -3.223964580411365e-1,
        -2.400758277161838e0,
        -2.549732539343734e0,
        4.374664141464968e0,
        2.938163982698783e0,
    ]
    d = [
        7.784695709041462e-3,
        3.224671290700398e-1,
        2.445134137142996e0,
        3.754408661907416e0,
    ]
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
        )
    q = math.sqrt(-2.0 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


def _bca_paired_ci(
    diffs: list[float],
    *,
    n_resamples: int,
    confidence: float,
    rng: random.Random,
) -> tuple[float, float] | None:
    """Bias-corrected and accelerated (BCa) bootstrap CI for median(diffs).

    Per "When +1% Is Not Enough" (arxiv 2511.19794, Nov 2025): the
    field-standard for small-sample paired comparisons. Adjusts the
    naive percentile CI for two pathologies common at small N:
      - bias-correction (z0): when the bootstrap distribution is shifted
        relative to the point estimate
      - acceleration (a): when the standard error depends on the
        parameter value (skewed sampling distribution)

    Returns None if fewer than 2 paired diffs (BCa is undefined).
    """
    n = len(diffs)
    if n < 2:
        return None
    point = statistics.median(diffs)
    # Bootstrap distribution.
    boot: list[float] = []
    for _ in range(n_resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot.append(statistics.median(sample))
    boot.sort()
    # z0: bias-correction
    n_below = sum(1 for b in boot if b < point)
    prop = n_below / n_resamples
    # Guard against prop in {0, 1} → infinite z0.
    prop = min(max(prop, 1.0 / (2.0 * n_resamples)), 1.0 - 1.0 / (2.0 * n_resamples))
    z0 = _normal_ppf(prop)
    # a: acceleration via jackknife
    jack = []
    for i in range(n):
        leave_one_out = diffs[:i] + diffs[i + 1 :]
        jack.append(statistics.median(leave_one_out))
    jack_mean = sum(jack) / n
    num = sum((jack_mean - j) ** 3 for j in jack)
    den = 6.0 * (sum((jack_mean - j) ** 2 for j in jack)) ** 1.5
    a = 0.0 if den == 0.0 else num / den
    # Adjusted alpha endpoints.
    alpha = (1.0 - confidence) / 2.0
    z_lo = _normal_ppf(alpha)
    z_hi = _normal_ppf(1.0 - alpha)
    p_lo = _normal_cdf(z0 + (z0 + z_lo) / (1.0 - a * (z0 + z_lo)))
    p_hi = _normal_cdf(z0 + (z0 + z_hi) / (1.0 - a * (z0 + z_hi)))
    lo_idx = max(0, min(n_resamples - 1, int(p_lo * n_resamples)))
    hi_idx = max(0, min(n_resamples - 1, int(p_hi * n_resamples) - 1))
    return boot[lo_idx], boot[hi_idx]


def _sign_flip_permutation_pvalue(
    diffs: list[float],
    *,
    n_perms: int,
    rng: random.Random,
) -> float | None:
    """Two-sided p-value via sign-flip permutation on paired diffs.

    Per "When +1% Is Not Enough" (arxiv 2511.19794): pair-symmetric H0
    is `recipe and baseline are interchangeable`, so flipping signs of
    paired differences is the right exchangeability test. Companion to
    BCa; the ship-rule requires BOTH to be significant.
    """
    n = len(diffs)
    if n < 2:
        return None
    observed = abs(sum(diffs) / n)
    n_extreme = 0
    for _ in range(n_perms):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(sum(flipped) / n) >= observed:
            n_extreme += 1
    return (n_extreme + 1) / (n_perms + 1)


def _per_pr_values(report: MultiRunReport, metric: str) -> dict[str, float]:
    """Per-PR median value of `metric` across all runs in a MultiRunReport.

    Skips per-sample entries where the metric value is None (e.g.
    detection_rate when the gold dataset has no defects on that PR).
    """
    bucket: dict[str, list[float]] = {}
    for run in report.per_run:
        for s in run.per_sample:
            mr = (s.metrics or {}).get(metric)
            if mr is None:
                continue
            v = getattr(mr, "value", None) if not isinstance(mr, dict) else mr.get("value")
            if isinstance(v, (int, float)):
                bucket.setdefault(s.pr_url, []).append(float(v))
    return {pr: statistics.median(vs) for pr, vs in bucket.items() if vs}


def compare_to_baseline_paired_bootstrap(
    recipe_report: MultiRunReport,
    baseline_report: MultiRunReport,
    *,
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
    use_bca: bool = True,
    permutation_alpha: float = 0.05,
    n_perms: int = 10000,
) -> ComparisonReport:
    """Per-PR paired bootstrap CI verdict (stronger than run-level CI).

    With use_bca=True (default), implements the "When +1% Is Not Enough"
    (arxiv 2511.19794, Nov 2025) ship-rule:
      verdict = above_noise iff (BCa CI excludes 0) AND (sign-flip
      permutation p-value < permutation_alpha).
    Both must pass — the bootstrap and permutation tests are
    complementary, and the paper rejects relying on either alone.

    With use_bca=False, falls back to the old percentile-bootstrap path
    (kept for back-compat with prior comparison JSONs on disk).

    For each metric:
      - Pair recipe and baseline by `pr_url`; for each PR take the median
        across runs on each side; skip PRs where either side is None.
      - Compute per-PR paired differences (recipe minus baseline).
      - BCa: bias-correct + acceleration-adjust the bootstrap CI.
      - Permutation: sign-flip H0 (recipe and baseline interchangeable).
      - Polarity-aware verdict (LOWER_IS_BETTER metrics flipped).

    Paired bootstrap eliminates PR-difficulty as a confound, which makes
    it substantially more powerful than the run-level CI for small N.
    """
    rng = random.Random(seed)
    metric_names: set[str] = set()
    metric_names.update(recipe_report.metric_bands.keys())
    metric_names.update(baseline_report.metric_bands.keys())

    entries: list[ComparisonEntry] = []
    method = (
        f"bca_paired_{int(confidence * 100)}+permutation_p{permutation_alpha}"
        if use_bca
        else f"paired_bootstrap_percentile_{int(confidence * 100)}"
    )
    for name in sorted(metric_names):
        r_band = recipe_report.metric_bands.get(name)
        b_band = baseline_report.metric_bands.get(name)
        r_med_top = r_band.median if r_band else None
        b_med_top = b_band.median if b_band else None
        if r_med_top is None or b_med_top is None:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med_top,
                    baseline_median=b_med_top,
                    delta=None,
                    verdict=None,
                )
            )
            continue
        r_per_pr = _per_pr_values(recipe_report, name)
        b_per_pr = _per_pr_values(baseline_report, name)
        common = sorted(set(r_per_pr) & set(b_per_pr))
        paired_diffs = [r_per_pr[pr] - b_per_pr[pr] for pr in common]
        if len(paired_diffs) < 2:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med_top,
                    baseline_median=b_med_top,
                    delta=r_med_top - b_med_top,
                    verdict="in_noise",
                    ci_method=method + "_insufficient_pairs",
                )
            )
            continue
        n = len(paired_diffs)
        if use_bca:
            ci = _bca_paired_ci(
                paired_diffs, n_resamples=n_resamples, confidence=confidence, rng=rng
            )
            pval = _sign_flip_permutation_pvalue(paired_diffs, n_perms=n_perms, rng=rng)
        else:
            # Percentile bootstrap (back-compat path).
            boot_medians: list[float] = []
            for _ in range(n_resamples):
                sample = [paired_diffs[rng.randrange(n)] for _ in range(n)]
                boot_medians.append(statistics.median(sample))
            boot_medians.sort()
            alpha = (1.0 - confidence) / 2.0
            lo_idx = max(0, int(alpha * n_resamples))
            hi_idx = min(n_resamples - 1, int((1.0 - alpha) * n_resamples) - 1)
            ci = (boot_medians[lo_idx], boot_medians[hi_idx])
            pval = None
        if ci is None:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med_top,
                    baseline_median=b_med_top,
                    delta=r_med_top - b_med_top,
                    verdict="in_noise",
                    ci_method=f"{method}_insufficient_pairs_n{n}",
                )
            )
            continue
        lo, hi = ci
        delta = r_med_top - b_med_top
        # Per-metric "ci_excludes_zero" on the polarity-correct side.
        if name in LOWER_IS_BETTER:
            ci_says_better = hi < 0
            ci_says_worse = lo > 0
        else:
            ci_says_better = lo > 0
            ci_says_worse = hi < 0
        verdict: Verdict
        if use_bca:
            # Combined gate: BOTH CI excludes 0 AND permutation p < alpha.
            perm_significant = pval is not None and pval < permutation_alpha
            if ci_says_better and perm_significant:
                verdict = "above_noise"
            elif ci_says_worse and perm_significant:
                verdict = "below_noise"
            else:
                verdict = "in_noise"
        else:
            verdict = (
                "above_noise"
                if ci_says_better
                else ("below_noise" if ci_says_worse else "in_noise")
            )
        entries.append(
            ComparisonEntry(
                metric=name,
                recipe_median=r_med_top,
                baseline_median=b_med_top,
                delta=delta,
                verdict=verdict,
                ci_lower=lo,
                ci_upper=hi,
                ci_method=f"{method}_n{n}",
                permutation_pvalue=pval,
            )
        )

    return ComparisonReport(
        noise_floor=0.0,
        n_runs_recipe=recipe_report.n_runs,
        n_runs_baseline=baseline_report.n_runs,
        per_metric=entries,
    )


def compare_to_baseline_ci(
    recipe_report: MultiRunReport,
    baseline_report: MultiRunReport,
    *,
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> ComparisonReport:
    """Per-metric bootstrap-CI verdict (replacement for hand-picked noise_floor).

    For each metric:
      - Pull per-run values from `recipe_report.per_run` and
        `baseline_report.per_run`.
      - Percentile-bootstrap the median-difference distribution.
      - `above_noise` iff the entire CI is on the "better" side of 0.
      - `below_noise` iff the entire CI is on the "worse" side of 0.
      - `in_noise` otherwise (CI straddles zero).

    With small N this often returns `in_noise` — which is the *correct*
    answer when the data cannot distinguish recipe from baseline.

    `noise_floor` in the resulting report is set to 0.0 because the
    verdict is no longer threshold-based.
    """
    rng = random.Random(seed)
    metric_names: set[str] = set()
    metric_names.update(recipe_report.metric_bands.keys())
    metric_names.update(baseline_report.metric_bands.keys())

    entries: list[ComparisonEntry] = []
    method = f"bootstrap_percentile_{int(confidence * 100)}"
    for name in sorted(metric_names):
        r_band = recipe_report.metric_bands.get(name)
        b_band = baseline_report.metric_bands.get(name)
        r_med = r_band.median if r_band else None
        b_med = b_band.median if b_band else None
        if r_med is None or b_med is None:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med,
                    baseline_median=b_med,
                    delta=None,
                    verdict=None,
                )
            )
            continue
        r_vals = _per_run_values(recipe_report, name)
        b_vals = _per_run_values(baseline_report, name)
        ci = _bootstrap_delta_ci(r_vals, b_vals, n_resamples, confidence, rng)
        if ci is None:
            # Per-run values unavailable; fall back to verdict-from-medians,
            # but without a CI we have to be honest and mark in_noise.
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med,
                    baseline_median=b_med,
                    delta=r_med - b_med,
                    verdict="in_noise",
                    ci_method=method + "_unavailable",
                )
            )
            continue
        lo, hi = ci
        delta = r_med - b_med
        verdict: Verdict
        if name in LOWER_IS_BETTER:
            # Better = recipe BELOW baseline; CI on raw delta must be entirely negative.
            if hi < 0:
                verdict = "above_noise"
            elif lo > 0:
                verdict = "below_noise"
            else:
                verdict = "in_noise"
        else:
            if lo > 0:
                verdict = "above_noise"
            elif hi < 0:
                verdict = "below_noise"
            else:
                verdict = "in_noise"
        entries.append(
            ComparisonEntry(
                metric=name,
                recipe_median=r_med,
                baseline_median=b_med,
                delta=delta,
                verdict=verdict,
                ci_lower=lo,
                ci_upper=hi,
                ci_method=method,
            )
        )

    return ComparisonReport(
        noise_floor=0.0,  # CI-driven, not floor-driven
        n_runs_recipe=recipe_report.n_runs,
        n_runs_baseline=baseline_report.n_runs,
        per_metric=entries,
    )


def render_comparison_summary(report: ComparisonReport) -> str:
    """Markdown summary of recipe-vs-baseline verdicts."""
    has_ci = any(e.ci_lower is not None for e in report.per_metric)
    lines: list[str] = []
    lines.append("# Recipe vs Baseline comparison")
    lines.append("")
    if has_ci:
        method = next((e.ci_method for e in report.per_metric if e.ci_method), "bootstrap")
        lines.append(
            f"recipe: N={report.n_runs_recipe} runs; baseline: N={report.n_runs_baseline} runs; "
            f"verdict gate: {method} (CI excludes 0)"
        )
    else:
        lines.append(
            f"recipe: N={report.n_runs_recipe} runs; baseline: N={report.n_runs_baseline} runs; "
            f"noise_floor: {report.noise_floor}"
        )
    lines.append("")
    if has_ci:
        lines.append("| metric | recipe_median | baseline_median | delta | 95% CI | verdict |")
        lines.append("|---|---:|---:|---:|:---:|:---|")
    else:
        lines.append("| metric | recipe_median | baseline_median | delta | verdict |")
        lines.append("|---|---:|---:|---:|:---|")
    for e in report.per_metric:
        verdict_str: str = str(e.verdict) if e.verdict else "n/a"
        if e.verdict == "above_noise":
            verdict_str = f"✓ {e.verdict}"
        elif e.verdict == "below_noise":
            verdict_str = f"✗ {e.verdict}"
        elif e.verdict == "in_noise":
            verdict_str = f"— {e.verdict}"
        if e.metric in LOWER_IS_BETTER:
            verdict_str += " (lower-is-better)"
        if has_ci:
            ci_str = (
                f"[{e.ci_lower:+.4f}, {e.ci_upper:+.4f}]"
                if e.ci_lower is not None and e.ci_upper is not None
                else "n/a"
            )
            lines.append(
                f"| {e.metric} | "
                f"{_fmt(e.recipe_median)} | {_fmt(e.baseline_median)} | "
                f"{_fmt(e.delta)} | {ci_str} | {verdict_str} |"
            )
        else:
            lines.append(
                f"| {e.metric} | "
                f"{_fmt(e.recipe_median)} | {_fmt(e.baseline_median)} | "
                f"{_fmt(e.delta)} | {verdict_str} |"
            )
    lines.append("")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.4f}" if v < 0 or v > 0 else f"{v:.4f}"


# ---------------------------------------------------------------------------
# Multi-objective verdict (multi-objective-v01)
# ---------------------------------------------------------------------------


Overall = Literal["keep", "discard", "ambiguous"]


class RecipeVerdict(BaseModel):
    """Vector classification of a recipe vs baseline.

    Derived from a `ComparisonReport`'s per-metric verdicts. The
    `overall` field replaces scalar utility as the keep/discard
    primitive for the autoresearch loop. Per-metric entries are
    preserved verbatim so downstream consumers (frontier rendering,
    `peer autoresearch frontier`) can read the full vector.
    """

    model_config = ConfigDict(extra="forbid")

    overall: Overall
    n_above_noise: int
    n_in_noise: int
    n_below_noise: int
    n_unmeasured: int
    per_metric: list[ComparisonEntry] = Field(default_factory=list)


def classify_comparison(report: ComparisonReport) -> RecipeVerdict:
    """Pure Pareto classifier over per-metric verdicts.

    keep:      ≥1 above_noise AND zero below_noise  (strict Pareto improvement)
    discard:   ≥1 below_noise AND zero above_noise  (strict regression)
    ambiguous: everything else (mixed signal or all in_noise)

    Per-metric verdicts already honor polarity (LOWER_IS_BETTER), so the
    Pareto test here is symmetric — a +cpp regression is below_noise on
    the entry, which correctly counts as a regression in the tally.

    Entries with verdict=None (unmeasured) are counted but do not
    participate in the keep/discard test.
    """
    n_above = sum(1 for e in report.per_metric if e.verdict == "above_noise")
    n_in = sum(1 for e in report.per_metric if e.verdict == "in_noise")
    n_below = sum(1 for e in report.per_metric if e.verdict == "below_noise")
    n_unmeasured = sum(1 for e in report.per_metric if e.verdict is None)

    overall: Overall
    if n_above >= 1 and n_below == 0:
        overall = "keep"
    elif n_below >= 1 and n_above == 0:
        overall = "discard"
    else:
        overall = "ambiguous"

    return RecipeVerdict(
        overall=overall,
        n_above_noise=n_above,
        n_in_noise=n_in,
        n_below_noise=n_below,
        n_unmeasured=n_unmeasured,
        per_metric=list(report.per_metric),
    )


def render_recipe_verdict(verdict: RecipeVerdict) -> str:
    """One-screen markdown summarising the vector verdict + reasoning."""
    label = {
        "keep": "✓ KEEP",
        "discard": "✗ DISCARD",
        "ambiguous": "? AMBIGUOUS",
    }[verdict.overall]
    lines: list[str] = []
    lines.append(f"# RecipeVerdict: {label}")
    lines.append("")
    lines.append(
        f"above_noise: {verdict.n_above_noise}  |  "
        f"in_noise: {verdict.n_in_noise}  |  "
        f"below_noise: {verdict.n_below_noise}  |  "
        f"unmeasured: {verdict.n_unmeasured}"
    )
    lines.append("")
    if verdict.overall == "keep":
        wins = [e.metric for e in verdict.per_metric if e.verdict == "above_noise"]
        lines.append(
            f"Strict Pareto improvement over baseline: wins on {', '.join(wins)}; no regressions."
        )
    elif verdict.overall == "discard":
        regressions = [e.metric for e in verdict.per_metric if e.verdict == "below_noise"]
        lines.append(f"Strict regression: regresses on {', '.join(regressions)}; no wins.")
    else:
        wins = [e.metric for e in verdict.per_metric if e.verdict == "above_noise"]
        regressions = [e.metric for e in verdict.per_metric if e.verdict == "below_noise"]
        if wins and regressions:
            lines.append(
                f"Mixed signal: wins on {', '.join(wins)} but regresses on {', '.join(regressions)}. "
                "Decision requires explicit metric preference."
            )
        else:
            lines.append("All metrics within noise floor — no measurable difference from baseline.")
    lines.append("")
    return "\n".join(lines)
