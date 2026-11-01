"""Run an agent over a set of bugs, one bug at a time.

For each bug: download its image (and check it the first time), do every run of this agent
on it, grade each run with the official harness, then delete the image. Images are ~4 GB
each, so keeping only the one in use is what lets the experiment fit on this machine.
Finished runs (those with a resolved.json) are skipped, so an interrupted schedule can resume.
"""

import json
from collections.abc import Callable
from pathlib import Path

from lift_eval import images
from lift_eval.grade import grade_run
from lift_eval.spend import check_budget


def run_schedule(
    cfg: dict,
    instance_ids: list[str],
    run_names: list[str],
    run_one: Callable[[dict, str, str], Path],
    dir_for: Callable[[str, str], Path],
    expected_cost_per_run: float,
    keep_images: bool = False,
    log: Callable[[str], None] = print,
) -> dict[tuple[str, str], bool]:
    """run_one(cfg, instance_id, run_name) runs the agent once; dir_for(run_name, instance_id) is its folder."""
    checked = json.loads(images.REPORT_JSON.read_text()) if images.REPORT_JSON.exists() else {}
    outcome = {}
    for iid in instance_ids:
        todo = [r for r in run_names if not (dir_for(r, iid) / "resolved.json").exists()]
        for r in set(run_names) - set(todo):
            outcome[(iid, r)] = json.loads((dir_for(r, iid) / "resolved.json").read_text())[iid]
        if not todo:
            log(f"skip {iid}: all runs already graded")
            continue
        images.ensure_image(iid)
        if iid not in checked:
            images.record_check(iid)
        for run_name in todo:
            spent = check_budget(cfg["budget"]["total_spend_cap_usd"], expected_cost_per_run)
            log(f"run {iid} {run_name} (spent so far ${spent:.2f})")
            out_dir = run_one(cfg, iid, run_name)
            resolved = grade_run(out_dir, cfg["dataset"]["runs"], cfg["dataset"]["runs_split"])
            outcome[(iid, run_name)] = resolved[iid]
            log(f"  -> resolved={resolved[iid]}")
        if not keep_images:
            images.remove_image(iid)
    return outcome
