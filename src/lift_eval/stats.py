"""Numbers with honest uncertainty.

With 8 bugs, one bug is 12.5 percentage points, so every comparison comes with a bootstrap
confidence interval. The bootstrap resamples both sources of noise: which bugs (with replacement),
and which runs of each bug (with replacement). It makes no assumption about the shape of the data.
"""

import random
import statistics


def per_run_rates(outcomes: dict[str, list[bool]]) -> list[float]:
    """Share of bugs resolved in each run. outcomes: bug -> [resolved in run 1, run 2, ...]."""
    n_runs = min(len(v) for v in outcomes.values())
    return [sum(v[r] for v in outcomes.values()) / len(outcomes) for r in range(n_runs)]


def mean_rate(outcomes: dict[str, list[bool]]) -> float:
    """Average over bugs of each bug's success rate across runs."""
    return statistics.mean(sum(v) / len(v) for v in outcomes.values())


def bootstrap_diff(
    a: dict[str, list[bool]], b: dict[str, list[bool]], n: int = 10000, seed: int = 0
) -> tuple[float, float, float]:
    """mean_rate(b) - mean_rate(a), with a 95% percentile interval. Bugs are paired across the two arms."""
    rng = random.Random(seed)
    bugs = sorted(set(a) & set(b))
    point = mean_rate({k: b[k] for k in bugs}) - mean_rate({k: a[k] for k in bugs})
    diffs = []
    for _ in range(n):
        sample = [rng.choice(bugs) for _ in bugs]
        da = [statistics.mean(rng.choice(a[k]) for _ in a[k]) for k in sample]
        db = [statistics.mean(rng.choice(b[k]) for _ in b[k]) for k in sample]
        diffs.append(statistics.mean(db) - statistics.mean(da))
    diffs.sort()
    return point, diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
