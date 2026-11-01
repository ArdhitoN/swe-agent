"""Grade any run with the official SWE-bench harness, the same way for every agent.

A bug counts as resolved only if the official harness says so: the tests that should start
passing do pass, and the tests that already passed still pass.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from lift_eval.dockerenv import docker_env


def write_jsonl(preds_json: Path) -> Path:
    preds = json.loads(preds_json.read_text())
    out = preds_json.with_suffix(".jsonl")
    with out.open("w") as f:
        for pred in preds.values():
            f.write(json.dumps({**pred, "model_patch": pred.get("model_patch") or ""}) + "\n")
    return out


def grade_run(run_dir: Path, dataset: str, split: str = "test", workers: int = 2) -> dict:
    """Grade run_dir/preds.json. Test output and the report end up inside run_dir/grade/."""
    preds = json.loads((run_dir / "preds.json").read_text())
    instance_ids = sorted(preds)
    jsonl = write_jsonl(run_dir / "preds.json")
    grade_dir = run_dir / "grade"
    if grade_dir.exists():
        shutil.rmtree(grade_dir)  # results are cached by run id, so always start clean
    grade_dir.mkdir()
    run_id = "-".join(run_dir.parts[-2:])  # e.g. "A-run_1": unique per run
    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset,
        "--split", split,
        "--predictions_path", str(jsonl),
        "--instance_ids", *instance_ids,
        "--max_workers", str(workers),
        "--run_id", run_id,
        "--report_dir", str(grade_dir),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, env=docker_env(), cwd=grade_dir)
    report_files = [p for p in grade_dir.glob("*.json") if run_id in p.name]
    report = json.loads(report_files[0].read_text())
    resolved = set(report.get("resolved_ids", []))
    summary = {iid: iid in resolved for iid in instance_ids}
    (run_dir / "resolved.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
