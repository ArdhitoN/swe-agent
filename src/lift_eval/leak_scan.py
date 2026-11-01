"""Scan every trajectory, of every agent, for commands that could reveal the fix from outside the code.

The images contain no git history after the bug, but the containers do have internet access, so an
agent could download a newer version of the package. Our agent refuses such commands; the baseline
must stay unmodified, so we check what it actually ran instead.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from lift_eval.config import REPO_ROOT
from lift_eval.spend import RESULTS_DIR

REPORT = REPO_ROOT / "reports" / "leak_scan.md"
PATTERNS = {
    "git history beyond the current commit": r"\bgit\b[^|;&\n]*\s--all\b|\bgit\s+(fetch|pull|clone|reflog)\b",
    "package install or download": r"\b(pip|pip3|conda)\s+(install|download)\b",
    "network tool or URL": r"\b(curl|wget)\b|https?://(?!localhost|127\.0\.0\.1|testserver|example\.(com|org))",
    "network from code": r"\burllib\.request\b|\brequests\.(get|post)\b|\bhttp\.client\b",
}


def commands_in(traj: dict) -> list[tuple[str, bool]]:
    """(command text, was it refused) for each action in a trajectory."""
    out = []
    msgs = traj.get("messages", [])
    for i, msg in enumerate(msgs):
        for action in (msg.get("extra") or {}).get("actions", []) or []:
            if action.get("tool") not in (None, "bash"):
                continue
            cmd = action.get("command") or ""
            if action.get("tool") == "bash":
                cmd = (action.get("args") or {}).get("command", cmd)
            # our agent's refusals are visible in the tool replies right after this message
            replies = []
            for m in msgs[i + 1:]:
                if m.get("role") != "tool":
                    break
                replies.append(m.get("content") if isinstance(m.get("content"), str) else "")
            out.append((cmd, any(r.startswith("refused:") for r in replies)))
    return out


def scan(results_dir: Path = RESULTS_DIR) -> dict:
    findings = defaultdict(list)
    n_trajs = defaultdict(int)
    for path in sorted(results_dir.rglob("*.traj.json")):
        rel = path.relative_to(results_dir)
        arm = rel.parts[0]
        n_trajs[arm] += 1
        for cmd, refused in commands_in(json.loads(path.read_text())):
            for label, pattern in PATTERNS.items():
                if re.search(pattern, cmd):
                    findings[arm].append({"file": str(rel), "kind": label, "refused": refused, "command": cmd[:300]})
    return {"trajectories": dict(n_trajs), "findings": dict(findings)}


def write_report(result: dict) -> str:
    lines = ["# Leak scan", "", "Commands that could reveal the fix from outside the bug's own code, per agent.", "",
             "| Agent | Trajectories | Flagged commands | Of which refused |", "|---|---|---|---|"]
    for arm in sorted(result["trajectories"]):
        f = result["findings"].get(arm, [])
        lines.append(f"| {arm} | {result['trajectories'][arm]} | {len(f)} | {sum(x['refused'] for x in f)} |")
    for arm, items in sorted(result["findings"].items()):
        lines += ["", f"## {arm}", ""]
        for x in items[:50]:
            state = "refused" if x["refused"] else "**executed**"
            lines.append(f"- {state}, {x['kind']}: `{x['command'][:160]}` ({x['file']})")
    text = "\n".join(lines) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text)
    (REPORT.with_suffix(".json")).write_text(json.dumps(result, indent=2) + "\n")
    return text
