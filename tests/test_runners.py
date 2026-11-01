import json

from lift_eval.grade import write_jsonl
from lift_eval.runners.run_baseline import collect_costs, instance_filter, mini_command
from lift_eval.spend import BudgetExceeded, check_budget, total_spent

CFG = {
    "model": {"name": "openai/gpt-5-mini-2025-08-07", "service_tier": "flex", "reasoning_effort": None},
    "dataset": {"runs": "SWE-bench/SWE-bench_Verified", "runs_split": "test"},
}


def test_instance_filter_matches_exact_ids_only():
    import re

    pattern = instance_filter(["django__django-11790", "sphinx-doc__sphinx-8056"])
    assert re.match(pattern, "django__django-11790")
    assert not re.match(pattern, "django__django-117900")


def test_mini_command_uses_minis_own_config_and_only_api_settings(tmp_path):
    cmd = mini_command(CFG, ["django__django-11790"], tmp_path, workers=2)
    configs = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-c"]
    assert configs[0].endswith("benchmarks/swebench.yaml")
    assert configs[1:] == ["model.model_kwargs.service_tier=flex"]  # no agent settings are overridden
    assert cmd[cmd.index("--model") + 1] == "openai/gpt-5-mini-2025-08-07"


def test_collect_costs_and_budget_guard(tmp_path):
    run = tmp_path / "A" / "run_1"
    for iid, cost in [("bug_a", 0.4), ("bug_b", 0.1)]:
        (run / iid).mkdir(parents=True)
        traj = {"info": {"model_stats": {"instance_cost": cost, "api_calls": 3}, "exit_status": "Submitted"}}
        (run / iid / f"{iid}.traj.json").write_text(json.dumps(traj))
    costs = collect_costs(run)
    assert costs["bug_a"]["cost"] == 0.4
    assert total_spent(tmp_path) == 0.5
    assert check_budget(1.0, 0.4, tmp_path) == 0.5
    try:
        check_budget(1.0, 0.6, tmp_path)
        raise AssertionError("should have refused")
    except BudgetExceeded:
        pass


def test_write_jsonl_keeps_empty_patches(tmp_path):
    preds = {"a": {"instance_id": "a", "model_name_or_path": "m", "model_patch": None}}
    (tmp_path / "preds.json").write_text(json.dumps(preds))
    rows = [json.loads(line) for line in write_jsonl(tmp_path / "preds.json").read_text().splitlines()]
    assert rows == [{"instance_id": "a", "model_name_or_path": "m", "model_patch": ""}]
