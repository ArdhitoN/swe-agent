"""Our agent on one bug: several attempts inside one shared budget, then pick one patch with tests."""

import json
from pathlib import Path

import yaml

from gated_agent import prompts
from gated_agent.attempt import GatedAgent, patch_id
from gated_agent.budget import BugBudget
from gated_agent.model import GatedModel
from gated_agent.select.selector import Candidate, choose, evaluate
from gated_agent.tools import REPRO_ONLY_TOOLS


def mini_swebench_config() -> dict:
    """mini-swe-agent's own SWE-bench config. We reuse its environment and model API settings as-is."""
    from minisweagent.config import builtin_config_dir

    return yaml.safe_load((builtin_config_dir / "benchmarks" / "swebench.yaml").read_text())


def make_model(cfg: dict, allowed_tools: set[str] | None = None) -> GatedModel:
    kwargs = dict(mini_swebench_config()["model"].get("model_kwargs", {}))  # same API settings as the baseline
    if cfg["model"].get("service_tier"):
        kwargs["service_tier"] = cfg["model"]["service_tier"]
    if cfg["model"].get("reasoning_effort"):
        kwargs["reasoning_effort"] = cfg["model"]["reasoning_effort"]
    return GatedModel(model_name=cfg["model"]["name"], model_kwargs=kwargs, allowed_tools=allowed_tools)


def env_factory(instance: dict, docker_executable: str):
    """Fresh container for the bug, configured exactly like mini-swe-agent's SWE-bench environment."""
    from minisweagent.run.benchmarks.swebench import get_sb_environment

    env_cfg = dict(mini_swebench_config()["environment"])
    env_cfg["executable"] = docker_executable

    def make():
        return get_sb_environment({"environment": env_cfg}, instance)

    return make


def run_attempt(cfg, instance, make_env, *, step_limit, cost_limit, traj_path, hint="", lessons="", mode="fix"):
    env = make_env()
    try:
        allowed = REPRO_ONLY_TOOLS if mode == "repro" else None
        agent = GatedAgent(
            make_model(cfg, allowed), env, step_limit=step_limit, cost_limit=cost_limit, output_path=traj_path,
            localize_share=cfg["agent"]["localize_budget_share"], mode=mode,
            **({"instance_template": prompts.REPRO_ONLY_INSTANCE} if mode == "repro" else {}),
        )
        info = agent.run(instance["problem_statement"], strategy_hint=hint, lessons=lessons)
    finally:
        env.cleanup()
    return agent, info


def run_bug(cfg: dict, instance: dict, out_dir: Path, make_env, log=print) -> dict:
    budget = BugBudget(cfg["budget"]["per_bug_max_calls"], cfg["budget"]["per_bug_max_cost_usd"])
    n = cfg["agent"]["attempts_per_bug"]
    candidates, records, lessons = [], [], ""
    for k in range(n):
        if budget.exhausted():
            break
        calls, cost = budget.share(n - k)
        agent, info = run_attempt(
            cfg, instance, make_env, step_limit=calls, cost_limit=cost,
            traj_path=out_dir / "attempts" / f"attempt_{k + 1}.traj.json",
            hint=prompts.STRATEGY_HINTS[k % len(prompts.STRATEGY_HINTS)], lessons=lessons,
        )
        budget.spend(agent.n_calls, agent.cost)
        patch = info.get("submission") or ""
        records.append({
            "attempt": k + 1, "exit_status": info.get("exit_status"), "verified": bool(info.get("verified")),
            "api_calls": agent.n_calls, "cost": agent.cost, "patch_id": patch_id(patch) if patch else None,
            "has_repro": agent.repro_code is not None, "events": len(agent.events),
        })
        log(f"    attempt {k + 1}: {records[-1]['exit_status']} verified={records[-1]['verified']} "
            f"calls={agent.n_calls} cost=${agent.cost:.3f}")
        candidates.append(Candidate(f"attempt_{k + 1}", patch, agent.repro_code))
        lessons = info.get("lessons", "") if info.get("exit_status") == "Restart" else ""
        if cfg["agent"]["early_stop"] and sum(r["verified"] for r in records) >= 2:
            break  # two independently verified fixes: a third attempt rarely changes the outcome
    chosen, selection = select_patch(candidates, make_env)
    write_outputs(out_dir, instance["instance_id"], cfg["model"]["name"], chosen, selection, records,
                  {"cost": budget.cost, "api_calls": budget.calls})
    return selection


def select_patch(candidates: list[Candidate], make_env, extra_repros: list[str] = ()) -> tuple[str, dict]:
    if not any(c.patch.strip() for c in candidates):
        return "", {"chosen": None, "reason": "no candidate produced a patch", "evaluations": []}
    env = make_env()
    try:
        repros, evals = evaluate(env, candidates, extra_repros)
    finally:
        env.cleanup()
    idx, reason = choose(evals)
    selection = {
        "chosen": candidates[idx].name if idx is not None else None,
        "reason": reason,
        "pooled_reproductions": len(repros),
        "evaluations": [
            {"name": e.name, "applies": e.applies, "repro_passes": list(e.repro_passes),
             "regressions": e.regressions, "patch_lines": e.patch_lines, "eligible": e.eligible}
            for e in evals
        ],
    }
    return (candidates[idx].patch if idx is not None else ""), selection


def write_outputs(out_dir, instance_id, model_name, patch, selection, records, totals):
    out_dir.mkdir(parents=True, exist_ok=True)
    preds = {instance_id: {"model_name_or_path": model_name, "instance_id": instance_id, "model_patch": patch}}
    (out_dir / "preds.json").write_text(json.dumps(preds, indent=2) + "\n")
    (out_dir / "attempts.json").write_text(json.dumps(records, indent=2) + "\n")
    (out_dir / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    (out_dir / "costs.json").write_text(json.dumps({instance_id: totals}, indent=2) + "\n")
