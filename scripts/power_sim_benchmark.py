"""Power simulation: minimum #PRs to detect a reviewer gap under peer's gate.

Answers "how much labeled data do we need?" for the benchmark, using the SAME
verdict gate peer uses to call a difference real (per 'When +1% Is Not Enough'):
  a difference counts as signal iff the bootstrap 95% CI on the mean paired
  per-PR difference excludes 0 AND the sign-flip permutation p < 0.05.

Model (deliberately conservative, calibrated to the market):
  - Each PR carries k gold defects, k ~ 1 + Poisson(mean_defects-1)  (>=1).
  - Each PR has a shared "catchability" random effect (difficulty) that shifts
    BOTH reviewers — this is what makes the paired design powerful (the effect
    cancels in the per-PR difference, the way real correlated reviews do).
  - Reviewer catches each defect ~ Bernoulli(clip(p_base + difficulty)).
  - Metric per PR = fraction of that PR's gold defects the reviewer caught.
  - Paired difference per PR = rate_A - rate_B; we test mean difference != 0.

Outputs a power curve over N (PR count) for several true gaps, plus the
false-positive rate at the null (gap = 0) to confirm the gate's calibration.

Run: uv run python scripts/power_sim_benchmark.py
No network, no LLM.
"""

from __future__ import annotations

import numpy as np

RNG = np.random.default_rng(20260531)

# Gate / sim sizes. Bootstrap+perm are vectorized so these are cheap.
N_SIMS = 1500
N_BOOT = 800
N_PERM = 800
ALPHA = 0.05

# Metric model.
P_BASE_B = 0.40  # baseline reviewer detection (~CodeRabbit-ish 46%, rounded down)
MEAN_DEFECTS_PER_PR = 3.0  # multi-defect PRs (the point of concentrating on big repos)
DIFFICULTY_SD = 0.15  # per-PR shared catchability spread (correlates the pair)


def _gold_counts(n_prs: int) -> np.ndarray:
    k = 1 + RNG.poisson(MEAN_DEFECTS_PER_PR - 1, size=n_prs)
    return np.clip(k, 1, None)


def _per_pr_rates(counts: np.ndarray, p_base: float, difficulty: np.ndarray) -> np.ndarray:
    """Vectorized: for each PR, mean of Bernoulli catches over its defects."""
    p = np.clip(p_base + difficulty, 0.01, 0.99)
    rates = np.empty(len(counts))
    for i, k in enumerate(counts):
        rates[i] = RNG.binomial(1, p[i], size=int(k)).mean()
    return rates


def _gate_fires(diffs: np.ndarray) -> bool:
    """peer's verdict gate: bootstrap CI on the mean paired diff excludes 0 AND
    sign-flip permutation p < 0.05."""
    n = len(diffs)
    if n < 2:
        return False
    # Bootstrap CI on the mean.
    idx = RNG.integers(0, n, size=(N_BOOT, n))
    boot_means = diffs[idx].mean(axis=1)
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    ci_excludes_0 = lo > 0 or hi < 0
    if not ci_excludes_0:
        return False
    # Sign-flip permutation test on the mean.
    obs = abs(diffs.mean())
    signs = RNG.choice([-1.0, 1.0], size=(N_PERM, n))
    perm_means = np.abs((signs * diffs).mean(axis=1))
    p = (1 + np.count_nonzero(perm_means >= obs)) / (N_PERM + 1)
    return p < ALPHA


def power_at(n_prs: int, gap: float) -> float:
    fires = 0
    for _ in range(N_SIMS):
        counts = _gold_counts(n_prs)
        difficulty = RNG.normal(0, DIFFICULTY_SD, size=n_prs)
        rates_b = _per_pr_rates(counts, P_BASE_B, difficulty)
        rates_a = _per_pr_rates(counts, P_BASE_B + gap, difficulty)
        if _gate_fires(rates_a - rates_b):
            fires += 1
    return fires / N_SIMS


def main() -> None:
    ns = [15, 20, 30, 40, 50, 75, 100]
    gaps = {"0pp (NULL/FPR)": 0.0, "10pp": 0.10, "15pp": 0.15, "20pp": 0.20}

    print(f"Gate: bootstrap 95% CI excludes 0 AND sign-flip perm p<{ALPHA}")
    print(
        f"Model: baseline detect={P_BASE_B:.0%}, ~{MEAN_DEFECTS_PER_PR:.0f} defects/PR, "
        f"difficulty SD={DIFFICULTY_SD}"
    )
    print(f"({N_SIMS} sims/cell)\n")
    header = "  N  | " + " | ".join(f"{g:>14}" for g in gaps)
    print(header)
    print("-" * len(header))
    for n in ns:
        cells = []
        for gap in gaps.values():
            pw = power_at(n, gap)
            cells.append(f"{pw:>13.0%}")
        print(f"{n:>4} | " + " | ".join(cells))

    print("\nRead: 'power' = P(gate fires | true gap). NULL column = false-positive")
    print("rate (want <=~5%). Pick the smallest N whose power >= 80% for the gap")
    print("you need to resolve.")


if __name__ == "__main__":
    main()
