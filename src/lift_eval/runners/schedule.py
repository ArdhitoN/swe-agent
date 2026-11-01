"""Run an agent over a set of bugs, one bug at a time.

For each bug: download its image (and check it the first time), do every run of this agent
on it, grade each run with the official harness, then delete the image. Images are ~4 GB
each, so keeping only the one in use is what lets the experiment fit on this machine.
Finished runs (those with a resolved.json) are skipped, so an interrupted schedule can resume.
"""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lift_eval import images
from lift_eval.grade import grade_run
from lift_eval.spend import check_budget


def _log(msg: str) -> None:
    print(msg, flush=True)


def run_schedule(
    cfg: dict,
    instance_ids: list[str],
    run_names: list[str],
    run_one: Callable[[dict, str, str], Path],
    dir_for: Callable[[str, str], Path],
    expected_cost_per_run: float,
    keep_images: bool = False,
    log: Callable[[str], None] = _log,
    parallel: int = 1,
) -> dict[tuple[str, str], bool]:
    """run_one(cfg, instance_id, run_name) runs the agent once; dir_for(run_name, instance_id) is its folder.

    parallel > 1 runs several runs of the SAME bug at once. Each run has its own containers and
    folder, so runs stay independent; only the image is shared.
    """
    checked = json.loads(images.REPORT_JSON.read_text()) if images.REPORT_JSON.exists() else {}
    outcome = {}

    def one(iid: str, run_name: str) -> bool:
        out_dir = run_one(cfg, iid, run_name)
        resolved = grade_run(out_dir, cfg["dataset"]["runs"], cfg["dataset"]["runs_split"])[iid]
        log(f"  {iid} {run_name} -> resolved={resolved}")
        return resolved

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
        # The budget check covers every run that may be in flight at once.
        spent = check_budget(cfg["budget"]["total_spend_cap_usd"], expected_cost_per_run * min(parallel, len(todo)))
        log(f"run {iid}: {', '.join(todo)} (spent so far ${spent:.2f})")
        if parallel <= 1:
            for run_name in todo:
                check_budget(cfg["budget"]["total_spend_cap_usd"], expected_cost_per_run)
                outcome[(iid, run_name)] = one(iid, run_name)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {pool.submit(one, iid, r): r for r in todo}
                for fut in as_completed(futures):
                    outcome[(iid, futures[fut])] = fut.result()
        if not keep_images:
            images.remove_image(iid)
    return outcome
