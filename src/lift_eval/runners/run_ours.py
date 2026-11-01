"""Runners for our agent (Arm B), the control (Arm C) and the ablation (Arm D).

- Arm B: our full agent: several attempts in one shared budget, then test-based patch selection.
- Arm C: the control. Our same selector picks among 3 of the baseline's patches, using
  reproduction scripts written by a separate, small "test writer". If this does as well as Arm B,
  our gain comes from "more tries + picking", not from a better agent.
- Arm D: the ablation. Our agent's FIRST attempt only, graded on its own: is a single attempt
  of our agent better than a single run of the baseline?
"""

import json
import shutil
from pathlib import Path

from lift_eval.config import load_env
from lift_eval.dataset import get_instance
from lift_eval.dockerenv import docker_env, docker_executable
from lift_eval.spend import RESULTS_DIR

TEST_WRITER_CALLS = 30  # per test-writer run; it only writes and registers a reproduction
TEST_WRITER_COST = 0.30


def run_dir(arm: str, run_name: str, instance_id: str) -> Path:
    return RESULTS_DIR / arm / run_name / instance_id


def _prepare(arm, run_name, instance_id) -> Path:
    load_env()
    import os

    os.environ.update(docker_env())
    out = run_dir(arm, run_name, instance_id)
    if out.exists():
        shutil.rmtree(out)  # always a fresh folder, so nothing from an earlier run is reused
    out.mkdir(parents=True)
    return out


def run_ours(cfg: dict, instance_id: str, run_name: str) -> Path:
    from gated_agent.agent import env_factory, run_bug

    out = _prepare("B", run_name, instance_id)
    instance = get_instance(cfg, instance_id)
    run_bug(cfg, instance, out, env_factory(instance, docker_executable()))
    return out


def baseline_runs_for_control(run_name: str) -> list[str]:
    """Control run k uses baseline runs k, k+1, k+2 (so 3 control runs need 5 baseline runs)."""
    k = int(run_name.split("_")[1])
    return [f"run_{k + i}" for i in range(3)]


def run_control(cfg: dict, instance_id: str, run_name: str) -> Path:
    from gated_agent.agent import env_factory, run_attempt, select_patch, write_outputs
    from gated_agent.select.selector import Candidate

    out = _prepare("C", run_name, instance_id)
    instance = get_instance(cfg, instance_id)
    make_env = env_factory(instance, docker_executable())
    candidates = []
    for a_run in baseline_runs_for_control(run_name):
        preds = json.loads((RESULTS_DIR / "A" / a_run / instance_id / "preds.json").read_text())
        candidates.append(Candidate(f"baseline_{a_run}", preds[instance_id].get("model_patch") or ""))
    repros, records, total_cost, total_calls = [], [], 0.0, 0
    for k in range(len(candidates)):  # one reproduction per candidate, like our agent's attempts
        agent, info = run_attempt(
            cfg, instance, make_env, step_limit=TEST_WRITER_CALLS, cost_limit=TEST_WRITER_COST,
            traj_path=out / "test_writer" / f"writer_{k + 1}.traj.json", mode="repro",
        )
        total_cost, total_calls = total_cost + agent.cost, total_calls + agent.n_calls
        records.append({"writer": k + 1, "registered": agent.repro_code is not None, "api_calls": agent.n_calls,
                        "cost": agent.cost})
        if agent.repro_code:
            repros.append(agent.repro_code)
    patch, selection = select_patch(candidates, make_env, extra_repros=repros)
    write_outputs(out, instance_id, cfg["model"]["name"], patch, selection, records,
                  {"cost": total_cost, "api_calls": total_calls})
    return out


def build_ablation(cfg: dict, instance_id: str, run_name: str) -> Path:
    """Arm D costs nothing extra: it reuses attempt 1 of the matching Arm B run."""
    from gated_agent.agent import write_outputs

    b_dir = run_dir("B", run_name, instance_id)
    traj = json.loads((b_dir / "attempts" / "attempt_1.traj.json").read_text())
    patch = traj["info"].get("submission") or ""
    out = _prepare("D", run_name, instance_id)
    write_outputs(out, instance_id, cfg["model"]["name"], patch, {"source": f"B/{run_name} attempt 1"}, [],
                  {"cost": 0.0, "api_calls": 0})
    return out
