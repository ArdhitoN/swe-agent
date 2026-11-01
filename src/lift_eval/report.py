"""Build reports/summary.md from saved results only. No API key or Docker needed."""

import csv
import json
import statistics

from lift_eval.config import REPO_ROOT
from lift_eval.spend import RESULTS_DIR, total_spent
from lift_eval.stats import bootstrap_diff, mean_rate, per_run_rates

SUMMARY = REPO_ROOT / "reports" / "summary.md"
PER_TASK = REPO_ROOT / "reports" / "per_task.csv"
ARMS = {
    "A": "Baseline: mini-swe-agent, unmodified",
    "B": "Our agent",
    "C": "Control: our selector over 3 baseline patches",
    "D": "Ablation: our agent's first attempt only",
}


def load_outcomes(arm: str, bugs: list[str]) -> dict[str, list[bool]]:
    out = {}
    for iid in bugs:
        runs = sorted(RESULTS_DIR.glob(f"{arm}/run_*/{iid}/resolved.json"), key=lambda p: int(p.parts[-3].split("_")[1]))
        if runs:
            out[iid] = [json.loads(p.read_text())[iid] for p in runs]
    return out


def load_costs(arm: str, bugs: list[str]) -> list[float]:
    costs = []
    for iid in bugs:
        for p in RESULTS_DIR.glob(f"{arm}/run_*/{iid}/costs.json"):
            costs.append(json.loads(p.read_text())[iid]["cost"])
    return costs


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def build_report(bugs: list[str], verdicts: dict | None = None) -> str:
    data = {arm: load_outcomes(arm, bugs) for arm in ARMS}
    data = {arm: d for arm, d in data.items() if d and len(d) == len(bugs)}
    n = len(bugs)
    lines = ["# Results", "", f"{n} test bug{'s' if n != 1 else ''}. Each cell: in how many runs the bug was resolved.", ""]

    # per-bug table
    arms = list(data)
    lines += ["| Bug | " + " | ".join(arms) + " | Memorization check |", "|---|" + "---|" * len(arms) + "---|"]
    rows = []
    for iid in bugs:
        cells = [f"{sum(data[a][iid])}/{len(data[a][iid])}" for a in arms]
        verdict = (verdicts or {}).get(iid, {}).get("verdict", "")
        lines.append(f"| `{iid}` | " + " | ".join(cells) + f" | {verdict} |")
        rows.append([iid, *cells, verdict])

    # per-arm table
    lines += ["", f"| Agent | Mean resolved | Bugs resolved per run (of {n}) | Runs | Std across runs | Mean cost per bug |",
              "|---|---|---|---|---|---|"]
    for a in arms:
        rates = per_run_rates(data[a])
        std = statistics.stdev(rates) if len(rates) > 1 else 0.0
        costs = load_costs(a, bugs)
        cost = f"${statistics.mean(costs):.3f}" if costs else "n/a"
        lines.append(f"| {a}: {ARMS[a]} | {_pct(mean_rate(data[a]))} | {mean_rate(data[a]) * len(bugs):.2f} | "
                     f"{len(rates)} | {_pct(std)} | {cost} |")

    # comparisons
    comparisons = [("B", "A", "**Lift: our agent vs baseline**"), ("D", "A", "One attempt of ours vs one baseline run"),
                   ("B", "D", "Gain from extra attempts + selection"), ("B", "C", "Our agent vs the control")]
    lines += ["", f"| Comparison | Difference | 95% interval | In bugs (of {n}) |", "|---|---|---|---|"]
    for hi, lo, label in comparisons:
        if hi in data and lo in data:
            d, lo_ci, hi_ci = bootstrap_diff(data[lo], data[hi])
            lines.append(f"| {label} ({hi} − {lo}) | {d * 100:+.1f} pts | [{lo_ci * 100:+.1f}, {hi_ci * 100:+.1f}] | "
                         f"{d * len(bugs):+.2f} |")

    if verdicts:
        clean = [b for b in bugs if verdicts.get(b, {}).get("verdict") == "clean"]
        if clean and "A" in data and "B" in data:
            d, lo_ci, hi_ci = bootstrap_diff({k: data["A"][k] for k in clean}, {k: data["B"][k] for k in clean})
            lines += ["", f"**Lift on the {len(clean)} bugs judged clean** (not memorized or suspect): "
                          f"{d * 100:+.1f} pts, 95% interval [{lo_ci * 100:+.1f}, {hi_ci * 100:+.1f}]."]

    lines += ["", f"Total API spend recorded across all runs and checks: **${total_spent():.2f}**."]
    text = "\n".join(lines) + "\n"
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(text)
    with PER_TASK.open("w", newline="") as f:
        csv.writer(f).writerows([["bug", *arms, "memorization"], *rows])
    return text
