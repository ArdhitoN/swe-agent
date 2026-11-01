"""Choose the final patch among several candidates with tests, deterministically.

1. Pool the reproduction scripts from all attempts; keep those that fail on the original code.
2. Apply each candidate patch in turn; run every pooled reproduction and the related existing tests.
3. Drop candidates that don't apply, are empty, or cause new test failures.
4. Score = number of pooled reproductions the candidate makes pass.
5. Ties: prefer the biggest group of candidates with identical test results (a majority vote),
   then the smallest patch.
6. If nothing survives step 3, still submit the best-scoring candidate (an empty answer always
   fails), marked unverified.
"""

import base64
import shlex
from dataclasses import dataclass, field

from gated_agent.tools import ToolRunner


@dataclass
class Candidate:
    name: str
    patch: str
    repro_code: str | None = None


@dataclass
class Evaluation:
    name: str
    applies: bool = False
    repro_passes: tuple[bool, ...] = ()
    regressions: list[str] = field(default_factory=list)
    patch_lines: int = 0

    @property
    def score(self) -> int:
        return sum(self.repro_passes)

    @property
    def eligible(self) -> bool:
        return self.applies and self.patch_lines > 0 and not self.regressions


def choose(evals: list[Evaluation]) -> tuple[int | None, str]:
    """Index of the chosen candidate and a one-line reason. Pure function, so it's easy to test."""
    usable = [i for i, e in enumerate(evals) if e.applies and e.patch_lines > 0]
    if not usable:
        return None, "no candidate patch applies"
    eligible = [i for i in usable if evals[i].eligible]
    pool, verified = (eligible, True) if eligible else (usable, False)
    best = max(evals[i].score for i in pool)
    top = [i for i in pool if evals[i].score == best]
    groups: dict[tuple, list[int]] = {}
    for i in top:
        groups.setdefault(evals[i].repro_passes, []).append(i)
    biggest = max(len(g) for g in groups.values())
    finalists = [i for g in groups.values() if len(g) == biggest for i in g]
    pick = min(finalists, key=lambda i: (evals[i].patch_lines, i))
    how = "verified" if verified else "UNVERIFIED (every candidate had new test failures)"
    return pick, f"{how}; passes {best} pooled reproductions; group of {biggest} with identical results"


# Same order of fallbacks as the official SWE-bench grader, so a patch the grader would accept
# is never rejected here (that would make the baseline's patches look worse than they are).
APPLY_METHODS = [
    ("git apply --whitespace=nowarn /tmp/cand.diff", "git apply -R --whitespace=nowarn /tmp/cand.diff"),
    ("git apply --whitespace=nowarn --3way /tmp/cand.diff", "git checkout -- . && git clean -fdq -e '*.pyc'"),
    ("patch --batch --forward --fuzz=5 -p1 -i /tmp/cand.diff", "patch --batch -R --fuzz=5 -p1 -i /tmp/cand.diff"),
]


def apply_patch(tools: ToolRunner) -> int | None:
    for i, (cmd, _) in enumerate(APPLY_METHODS):
        if tools.sh(f"cd /testbed && {cmd}")["returncode"] == 0:
            return i
    return None


def revert_patch(tools: ToolRunner, method: int) -> None:
    tools.sh(f"cd /testbed && {APPLY_METHODS[method][1]}")


def _write(tools: ToolRunner, path: str, text: str) -> None:
    payload = base64.b64encode(text.encode()).decode()
    tools.sh(f"echo {payload} | base64 -d > {shlex.quote(path)}")


def evaluate(env, candidates: list[Candidate], extra_repros: list[str] = ()) -> tuple[list[str], list[Evaluation]]:
    """Run the pooled reproductions and regression checks for every candidate in one fresh container.

    The pool is every candidate's own reproduction plus `extra_repros` (scripts written separately,
    used when the candidates came from an agent that doesn't write reproductions).
    """
    tools = ToolRunner(env)
    repros = []
    codes = [c.repro_code for c in candidates if c.repro_code] + [r for r in extra_repros if r]
    for i, code in enumerate(dict.fromkeys(codes)):
        path = f"/tmp/pool_repro_{i}.py"
        _write(tools, path, code)
        _, data = tools.call("run_script", {"path": path})
        if data.get("exit_code", 0) != 0:  # must fail on the original code to count
            repros.append(path)
    evals = []
    for c in candidates:
        e = Evaluation(name=c.name, patch_lines=sum(
            1 for l in c.patch.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))
        ))
        method = None
        if e.patch_lines:
            _write(tools, "/tmp/cand.diff", c.patch)
            method = apply_patch(tools)
            e.applies = method is not None
        if e.applies:
            e.repro_passes = tuple(tools.call("run_script", {"path": p})[1].get("exit_code") == 0 for p in repros)
            _, reg = tools.call("regression_check", {}, timeout=2400)
            e.regressions = reg.get("regressions", []) + (["<test run broke>"] if reg.get("broke_run") else [])
            revert_patch(tools, method)
        evals.append(e)
    return repros, evals
