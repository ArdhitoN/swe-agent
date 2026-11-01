"""The baseline: mini-swe-agent, unmodified, through its own SWE-bench batch runner and config.

We only choose *which* bugs, *which* model and *where* the output goes. The agent, its prompts,
its step limit (250) and cost limit ($3) all come from mini-swe-agent's own `swebench.yaml`.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lift_eval.config import REPO_ROOT, load_env
from lift_eval.dockerenv import docker_env
from lift_eval.spend import RESULTS_DIR

BASELINE_CONFIG_COPY = REPO_ROOT / "configs" / "baseline_mini.yaml"


def mini_config_path() -> Path:
    from minisweagent.config import builtin_config_dir

    return builtin_config_dir / "benchmarks" / "swebench.yaml"


def record_baseline_config() -> str:
    """Copy mini-swe-agent's own config into the repo and return its hash, to show it was used unchanged."""
    src = mini_config_path()
    BASELINE_CONFIG_COPY.write_text(src.read_text())
    return hashlib.sha256(src.read_bytes()).hexdigest()


def instance_filter(instance_ids: list[str]) -> str:
    return "^(" + "|".join(re.escape(i) for i in instance_ids) + ")$"


def mini_command(cfg: dict, instance_ids: list[str], out_dir: Path, workers: int) -> list[str]:
    model = cfg["model"]
    cmd = [
        str(Path(sys.executable).parent / "mini-extra"),
        "swebench",
        "--subset", cfg["dataset"]["runs"],
        "--split", cfg["dataset"]["runs_split"],
        "--filter", instance_filter(instance_ids),
        "--model", model["name"],
        "-c", str(mini_config_path()),
        "-w", str(workers),
        "-o", str(out_dir),
    ]  # fmt: skip
    # API settings only (price tier, reasoning effort). They are applied identically to every agent.
    if model.get("service_tier"):
        cmd += ["-c", f"model.model_kwargs.service_tier={model['service_tier']}"]
    if model.get("reasoning_effort"):
        cmd += ["-c", f"model.model_kwargs.reasoning_effort={model['reasoning_effort']}"]
    return cmd


def collect_costs(out_dir: Path) -> dict:
    """Cost and model calls per bug, read from mini-swe-agent's own trajectory files."""
    costs = {}
    for traj in out_dir.glob("*/*.traj.json"):
        info = json.loads(traj.read_text())["info"]
        stats = info.get("model_stats", {})
        costs[traj.parent.name] = {
            "cost": stats.get("instance_cost", 0.0),
            "api_calls": stats.get("api_calls", 0),
            "exit_status": info.get("exit_status"),
        }
    (out_dir / "costs.json").write_text(json.dumps(costs, indent=2, sort_keys=True) + "\n")
    return costs


def run_dir(arm: str, run_name: str, instance_id: str) -> Path:
    """One folder per (agent, run, bug), e.g. results/A/run_1/django__django-11790/."""
    return RESULTS_DIR / arm / run_name / instance_id


def run_baseline(cfg: dict, instance_id: str, run_name: str, arm: str = "A") -> Path:
    """Run the unmodified baseline on one bug, once."""
    load_env()
    out_dir = run_dir(arm, run_name, instance_id)
    if out_dir.exists():
        # Always a fresh folder: mini-swe-agent skips bugs already in an existing preds.json,
        # which would silently reuse an earlier run's answer.
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    meta = {"baseline_config_sha256": record_baseline_config(), "instance_id": instance_id, "run": run_name}
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    cmd = mini_command(cfg, [instance_id], out_dir, workers=1)
    (out_dir / "command.txt").write_text(" ".join(cmd) + "\n")
    with (out_dir / "runner_output.log").open("w") as log:
        subprocess.run(cmd, check=True, env=docker_env(), cwd=out_dir, stdout=log, stderr=subprocess.STDOUT)
    collect_costs(out_dir)
    return out_dir
