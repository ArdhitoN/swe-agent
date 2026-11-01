"""Choose the test and dev bugs with a fixed, seeded rule.

The rule:
1. Score each pool bug by the fraction of public mini-swe-agent runs that fixed it,
   leaving out runs of our own model (so our baseline's results never influence the choice)
   and broken run records (see `usable_runs`).
2. Keep bugs whose score is inside [band_low, band_high]. Bugs that almost every model or
   almost no model fixes can't show a difference between two agents.
3. Draw the test bugs per repo (equal split) with the fixed seed written down beforehand.
4. Draw the dev bugs per repo from the rest of the band, skipping any bug whose gold patch
   touches a file that a test bug's gold patch touches. This stops knowledge from a dev bug
   leaking into a test bug, and the check compares file names only, so nobody reads the test fixes.
"""

import json
import random
from pathlib import Path

from lift_eval.config import REPO_ROOT
from lift_eval.snapshot import SNAPSHOT_DIR

TASKS_TEST = REPO_ROOT / "configs" / "tasks_test.txt"
TASKS_DEV = REPO_ROOT / "configs" / "tasks_dev.txt"
SELECTION_REPORT = REPO_ROOT / "reports" / "task_selection.md"

# A run record is treated as broken if its score on the pool is this far from its official score.
# Example: one public record shows 0% on the pool for a model with 69.6% officially.
MAX_POOL_VS_OFFICIAL_GAP_PCT = 30.0


def repo_of(instance_id: str) -> str:
    return instance_id.split("__")[0]


def usable_runs(runs: dict, pool: list[str], exclude_substring: str) -> dict:
    """Runs that report every pool bug, aren't our model, and whose pool score looks like their official score."""
    kept = {}
    for folder, run in runs.items():
        if exclude_substring and exclude_substring in folder:
            continue
        if set(run["pool_reported"]) != set(pool):
            continue
        pool_pct = 100 * sum(run["pool_resolved"].values()) / len(pool)
        if abs(pool_pct - run["official_resolved_pct"]) > MAX_POOL_VS_OFFICIAL_GAP_PCT:
            continue
        kept[folder] = run
    return kept


def solve_rates(runs: dict, pool: list[str]) -> dict[str, float]:
    return {iid: sum(r["pool_resolved"][iid] for r in runs.values()) / len(runs) for iid in pool}


def draw(
    rates: dict[str, float],
    gold_files: dict[str, list[str]],
    *,
    seed: int,
    band_low: float,
    band_high: float,
    test_per_repo: dict[str, int],
    dev_per_repo: dict[str, int],
) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    band = sorted(iid for iid, r in rates.items() if band_low <= r <= band_high)
    test = []
    for repo in sorted(test_per_repo):
        candidates = [iid for iid in band if repo_of(iid) == repo]
        test += sorted(rng.sample(candidates, test_per_repo[repo]))
    test_files = {f for iid in test for f in gold_files[iid]}
    dev = []
    for repo in sorted(dev_per_repo):
        candidates = [
            iid
            for iid in band
            if repo_of(iid) == repo and iid not in test and not (set(gold_files[iid]) & test_files)
        ]
        dev += sorted(rng.sample(candidates, dev_per_repo[repo]))
    return test, dev


def select_tasks(cfg: dict, snapshot_dir: Path = SNAPSHOT_DIR, write: bool = True) -> dict:
    sel = cfg["task_selection"]
    runs = json.loads((snapshot_dir / "runs.json").read_text())
    gold_files = json.loads((snapshot_dir / "gold_files.json").read_text())
    pool = sorted(gold_files)
    kept = usable_runs(runs, pool, sel["exclude_runs_matching"])
    rates = solve_rates(kept, pool)
    test, dev = draw(
        rates,
        gold_files,
        seed=sel["seed"],
        band_low=sel["band_low"],
        band_high=sel["band_high"],
        test_per_repo=sel["test_per_repo"],
        dev_per_repo=sel["dev_per_repo"],
    )
    result = {"test": test, "dev": dev, "rates": rates, "n_runs": len(kept), "n_runs_total": len(runs)}
    if write:
        TASKS_TEST.write_text("\n".join(test) + "\n")
        TASKS_DEV.write_text("\n".join(dev) + "\n")
        SELECTION_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SELECTION_REPORT.write_text(render_report(result, sel))
    return result


def render_report(result: dict, sel: dict) -> str:
    rates = result["rates"]
    band = [i for i, r in rates.items() if sel["band_low"] <= r <= sel["band_high"]]
    lines = [
        "# Bug selection",
        "",
        "Rule: score each bug by the share of public mini-swe-agent runs that fixed it; keep bugs inside the band; "
        "draw test bugs per repo with the seed; draw dev bugs from the rest of the band, skipping any that touch "
        "the same files as a test bug's fix. Full rule: `src/lift_eval/tasks.py`.",
        "",
        f"Seed `{sel['seed']}`, band {sel['band_low']:.0%}–{sel['band_high']:.0%}.",
        f"Difficulty is the share of **{result['n_runs']}** usable public mini-swe-agent runs "
        f"(of {result['n_runs_total']} in the snapshot) that fixed each bug. "
        f"Runs matching `{sel['exclude_runs_matching']}` (our own model) are excluded.",
        "",
        f"- Below the band: {sum(r < sel['band_low'] for r in rates.values())} bugs",
        f"- In the band: {len(band)} bugs",
        f"- Above the band: {sum(r > sel['band_high'] for r in rates.values())} bugs",
        "",
        "| Bug | Fixed by (share of runs) | Role |",
        "|---|---|---|",
    ]
    for iid in sorted(rates, key=lambda i: (rates[i], i)):
        role = "**test**" if iid in result["test"] else "dev" if iid in result["dev"] else ""
        lines.append(f"| `{iid}` | {rates[iid]:.0%} | {role} |")
    return "\n".join(lines) + "\n"
