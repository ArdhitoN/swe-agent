"""Which test bugs might the model have memorized?

These bugs and their fixes are public, so the model may have seen them during training. Four checks,
each with a threshold fixed in configs/experiment.yaml before any results were looked at:

- P1, issue-only file guess: given only the issue text (no code), does the model name the file the
  official fix changes? (Idea from "The SWE-Bench Illusion", arXiv 2506.12286.)
- P2, ID-only recall: given only the task ID and repo, can the model write the official fix?
  (Idea from OpenAI's Feb 2026 audit of SWE-bench Verified.) Best of 3 tries.
- P3, patch similarity: how close are the agents' final patches to the official fix?
- P4, too-early fix: did the agent edit a file within a few steps of first opening it?

Verdict per bug:
- memorized: P2 reaches its threshold, or P1, P3 and P4 all fire;
- suspect: one or two of P1, P3, P4 fire;
- clean: none fire.

The official fixes are used here, after the runs, for analysis only. No agent ever sees them.
"""

import difflib
import json
import re
from pathlib import Path

from lift_eval.config import REPO_ROOT, load_env
from lift_eval.dataset import get_instance
from lift_eval.snapshot import changed_files
from lift_eval.spend import RESULTS_DIR

REPORT = REPO_ROOT / "reports" / "contamination.md"
PROBES_DIR = RESULTS_DIR / "probes"
P2_TRIES = 3

P1_PROMPT = """Here is a GitHub issue from the {repo} repository.

<issue>
{issue}
</issue>

Without looking at the code, which source file(s) would most likely need to change to fix it?
Answer with repository-relative file paths only, one per line, most likely first. At most 3."""

P2_PROMPT = """The SWE-bench task `{instance_id}` comes from the {repo} repository.
From memory, write the code change (as a unified diff) that fixed it.
If you don't know it, answer exactly: unknown"""


def changed_lines(patch: str) -> list[str]:
    return [l[1:].strip() for l in patch.splitlines()
            if l[:1] in "+-" and not l.startswith(("+++", "---")) and l[1:].strip()]


def similarity(patch: str, gold: str) -> float:
    """0..1: how alike the changed lines of two patches are."""
    a, b = changed_lines(patch), changed_lines(gold)
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def _ask(cfg: dict, prompt: str) -> tuple[str, float]:
    import litellm

    kwargs = {"service_tier": cfg["model"]["service_tier"]} if cfg["model"].get("service_tier") else {}
    r = litellm.completion(model=cfg["model"]["name"], messages=[{"role": "user", "content": prompt}], **kwargs)
    return r.choices[0].message.content or "", litellm.completion_cost(r)


def run_probes(cfg: dict, instance_ids: list[str]) -> dict:
    """P1 and P2 (paid, small). Saved, with their cost, under results/probes/."""
    load_env()
    PROBES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROBES_DIR / "probes.json"
    data = json.loads(out_path.read_text()) if out_path.exists() else {}
    costs = {}
    for iid in instance_ids:
        if iid in data:
            continue
        inst = get_instance(cfg, iid)
        gold_files = changed_files(inst["patch"])
        p1_answer, c1 = _ask(cfg, P1_PROMPT.format(repo=inst["repo"], issue=inst["problem_statement"]))
        named = [l.strip().strip("`").lstrip("./") for l in p1_answer.splitlines() if l.strip()]
        p2_answers, c2 = [], 0.0
        for _ in range(P2_TRIES):
            ans, c = _ask(cfg, P2_PROMPT.format(instance_id=iid, repo=inst["repo"]))
            p2_answers.append(ans)
            c2 += c
        data[iid] = {
            "gold_files": gold_files,
            "p1_answer": p1_answer,
            "p1_correct": any(f in named for f in gold_files),
            "p2_answers": p2_answers,
            "p2_similarity": max(similarity(a, inst["patch"]) for a in p2_answers),
        }
        costs[iid] = {"cost": c1 + c2}
        out_path.write_text(json.dumps(data, indent=2) + "\n")
        prev = json.loads((PROBES_DIR / "costs.json").read_text()) if (PROBES_DIR / "costs.json").exists() else {}
        (PROBES_DIR / "costs.json").write_text(json.dumps({**prev, **costs}, indent=2) + "\n")
    return data


def _final_patches(arm: str, iid: str) -> list[str]:
    out = []
    for preds in sorted(RESULTS_DIR.glob(f"{arm}/run_*/{iid}/preds.json")):
        out.append(json.loads(preds.read_text())[iid].get("model_patch") or "")
    return out


def _too_early(traj_path: Path, max_steps: int) -> bool | None:
    """Did the first edit of a file come within max_steps of first looking at that file?"""
    msgs = json.loads(traj_path.read_text()).get("messages", [])
    first_seen, step = {}, 0
    for msg in msgs:
        actions = (msg.get("extra") or {}).get("actions") or []
        if not actions:
            continue
        step += 1
        for a in actions:
            tool, args = a.get("tool", "bash"), a.get("args") or {}
            text = args.get("command", "") if tool == "bash" else json.dumps(args)
            text = text or a.get("command", "")
            paths = set(re.findall(r"[\w./-]+\.py", text))
            is_edit = tool in ("edit", "create") or bool(re.search(r"sed -i|cat\s*>|>\s*[\w./-]+\.py|\.write\(", text))
            for p in paths:
                first_seen.setdefault(p, step)
                if is_edit and not p.startswith("/tmp") and "repro" not in p:
                    return step - first_seen[p] <= max_steps
    return None


def classify(cfg: dict, probes: dict, instance_ids: list[str]) -> dict:
    th = cfg["contamination"]
    verdicts = {}
    for iid in instance_ids:
        gold = get_instance(cfg, iid)["patch"]
        sims = {arm: [similarity(p, gold) for p in _final_patches(arm, iid)] for arm in ("A", "B")}
        p3_runs = [s for arm in sims.values() for s in arm]
        p3 = bool(p3_runs) and sum(s >= th["p3_similarity_near_identical"] for s in p3_runs) > len(p3_runs) / 2
        trajs = sorted(RESULTS_DIR.glob(f"A/run_*/{iid}/{iid}/*.traj.json")) + sorted(
            RESULTS_DIR.glob(f"B/run_*/{iid}/attempts/attempt_1.traj.json"))
        early = [e for e in (_too_early(t, th["p4_too_early_steps"]) for t in trajs) if e is not None]
        p4 = bool(early) and sum(early) > len(early) / 2
        pr = probes.get(iid, {})
        p1 = bool(pr.get("p1_correct"))
        p2 = pr.get("p2_similarity", 0.0) >= th["p2_similarity_memorized"]
        fired = sum([p1, p3, p4])
        verdict = "memorized" if p2 or fired == 3 else "suspect" if fired else "clean"
        verdicts[iid] = {"verdict": verdict, "p1_issue_only_file": p1, "p2_id_only_similarity": pr.get("p2_similarity"),
                         "p3_similarity_by_agent": sims, "p3_near_identical": p3,
                         "p4_too_early_share": (sum(early) / len(early)) if early else None, "p4_too_early": p4}
    return verdicts


def write_report(verdicts: dict, cfg: dict) -> str:
    th = cfg["contamination"]
    lines = [
        "# Memorization checks", "",
        "Could the model have memorized these bugs' fixes? Thresholds were fixed before looking at results:",
        f"P2 memorized at similarity ≥ {th['p2_similarity_memorized']}, P3 near-identical at ≥ "
        f"{th['p3_similarity_near_identical']}, P4 too early within {th['p4_too_early_steps']} steps.", "",
        "| Bug | Verdict | P1 file from issue alone | P2 fix from ID alone (similarity) | P3 near-identical to official fix | P4 edit too early |",
        "|---|---|---|---|---|---|",
    ]
    for iid, v in verdicts.items():
        share = v["p4_too_early_share"]
        lines.append(f"| `{iid}` | **{v['verdict']}** | {'yes' if v['p1_issue_only_file'] else 'no'} | "
                     f"{v['p2_id_only_similarity']} | {'yes' if v['p3_near_identical'] else 'no'} | "
                     f"{'n/a' if share is None else f'{share:.0%} of runs'} |")
    text = "\n".join(lines) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text)
    REPORT.with_suffix(".json").write_text(json.dumps(verdicts, indent=2) + "\n")
    return text
