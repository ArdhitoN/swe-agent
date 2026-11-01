"""Keep the whole experiment inside its API budget.

Every paid step writes a costs.json next to its results. Before a new paid step starts,
we add up everything spent so far and refuse to start if the budget would be exceeded.
"""

import json
from pathlib import Path

from lift_eval.config import REPO_ROOT

RESULTS_DIR = REPO_ROOT / "results"


class BudgetExceeded(RuntimeError):
    pass


def total_spent(results_dir: Path = RESULTS_DIR) -> float:
    total = 0.0
    for path in results_dir.rglob("costs.json"):
        total += sum(item.get("cost", 0.0) for item in json.loads(path.read_text()).values())
    return round(total, 4)


def check_budget(cap_usd: float, expected_usd: float, results_dir: Path = RESULTS_DIR) -> float:
    spent = total_spent(results_dir)
    if spent + expected_usd > cap_usd:
        raise BudgetExceeded(
            f"Spent ${spent:.2f} so far; this step may cost up to ${expected_usd:.2f}, "
            f"which would pass the ${cap_usd:.2f} cap."
        )
    return spent
