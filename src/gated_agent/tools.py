"""The agent's tools: what the model sees (schemas) and how each call is carried out.

Reading and editing tools run inside the bug's container through toolbox/toolbox.py.
`bash` is still available, but guarded: commands that could reveal the fix from outside the
bug's own code (other git history, the internet) are refused.
"""

import base64
import json
import re
from pathlib import Path

TOOLBOX_SRC = Path(__file__).parent / "toolbox" / "toolbox.py"
TOOLBOX_IN_CONTAINER = "/tmp/.gated/toolbox.py"
TOOLBOX_PY = "/opt/miniconda3/bin/python"  # the image's modern Python; the project's own Python may be old
RESULT_MARK = "@@RESULT@@ "


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_S = {"type": "string"}
_I = {"type": "integer"}

TOOL_SCHEMAS = [
    _tool("bash", "Run a shell command in /testbed. Not for editing source files (use `edit`). "
          "No network access and no git history beyond the current commit.", {"command": _S}, ["command"]),
    _tool("search", "Search tracked files for a regular expression (git grep). Returns file:line:text.",
          {"pattern": _S, "path": {"type": "string", "description": "file or folder, default the whole repo"}},
          ["pattern"]),
    _tool("outline", "List the classes and functions in a Python file, with line ranges.", {"path": _S}, ["path"]),
    _tool("view", "Show numbered lines of a file (at most 150 per call).",
          {"path": _S, "start": _I, "end": _I}, ["path"]),
    _tool("edit", "Replace ONE exact, unique occurrence of `old` with `new` in a source file. "
          "Copy `old` exactly from `view` output, without the line numbers. Python edits that break "
          "syntax or imports are undone automatically. Test files cannot be edited.",
          {"path": _S, "old": _S, "new": _S}, ["path", "old", "new"]),
    _tool("create", "Create a NEW source file (rarely needed).", {"path": _S, "content": _S}, ["path", "content"]),
    _tool("register_repro", "Register your reproduction script (a file under /tmp). It is run against the ORIGINAL "
          "code and must FAIL there (non-zero exit), showing the bug. Required before `verify`.",
          {"path": _S}, ["path"]),
    _tool("run_tests", "Run existing repo tests. Django: test labels like `forms_tests` or "
          "`forms_tests.tests.test_forms`. Others: pytest paths like `tests/test_build.py`.",
          {"targets": {"type": "array", "items": _S}}, ["targets"]),
    _tool("verify", "Check your fix: your reproduction must now pass, and related existing tests must not "
          "have new failures. `submit` only works after a successful `verify`.", {}, []),
    _tool("submit", "Submit your fix. Only accepted right after a successful `verify` with no edits since.", {}, []),
]

TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}
REPRO_ONLY_TOOLS = {"bash", "search", "outline", "view", "register_repro", "run_tests"}

# Commands our agent may not run. They could reveal the fix from outside the bug's own code.
_BLOCKED = [
    (r"\bgit\b[^|;&]*\s--all\b", "git commands over all branches/history"),
    (r"\bgit\s+(fetch|pull|clone|remote|reflog|cherry-pick)\b", "git commands that reach other history"),
    (r"\bgit\s+(checkout|switch|reset|restore)\b(?![^|;&]*\s--\s)", "moving to another git revision (use `edit`)"),
    (r"\b(pip|pip3|conda|mamba|apt|apt-get)\s+(install|download)\b", "installing or downloading packages"),
    (r"\b(curl|wget|nc|ssh|scp)\b", "network access"),
    (r"https?://", "network access"),
    (r"\b(urllib|requests|http\.client|socket)\b", "network access from code"),
    (r"\bsed\s+-i\b|\bperl\s+-pi\b", "in-place editing with sed/perl (use `edit`, which checks the result)"),
]


def blocked_reason(command: str) -> str | None:
    for pattern, reason in _BLOCKED:
        if re.search(pattern, command):
            return reason
    return None


def install_command() -> str:
    payload = base64.b64encode(TOOLBOX_SRC.read_bytes()).decode()
    return f"mkdir -p /tmp/.gated && echo {payload} | base64 -d > {TOOLBOX_IN_CONTAINER}"


def toolbox_command(name: str, args: dict) -> str:
    payload = base64.b64encode(json.dumps(args).encode()).decode()
    return f"{TOOLBOX_PY} {TOOLBOX_IN_CONTAINER} {name} {payload}"


def split_result(output: str) -> tuple[str, dict]:
    """Separate the model-facing text from the final machine-readable result line."""
    text, _, tail = output.rpartition(RESULT_MARK)
    if not _:
        return output, {}
    try:
        return text.rstrip(), json.loads(tail.strip().splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        return output, {}


class ToolRunner:
    """Runs toolbox commands in a mini-swe-agent environment (one container)."""

    def __init__(self, env):
        self.env = env
        out = env.execute({"command": install_command()})
        if out["returncode"] != 0:
            raise RuntimeError(f"could not install toolbox: {out['output'][-500:]}")

    def call(self, name: str, args: dict, timeout: int = 120) -> tuple[str, dict]:
        out = self.env.execute({"command": toolbox_command(name, args)}, timeout=timeout)
        text, data = split_result(out.get("output", ""))
        if out.get("exception_info"):
            text = f"{out['exception_info']}\n{text}"
            data.setdefault("ok", False)
        return text, data

    def sh(self, command: str, timeout: int = 60) -> dict:
        return self.env.execute({"command": command}, timeout=timeout)

    def source_diff(self) -> str:
        """The patch: changes to non-test source files only, including new files."""
        out = self.sh(
            "cd /testbed && git status --porcelain --untracked-files=all | awk '{print $2}' | "
            "grep -E '\\.py$' | grep -v -E '(^|/)(tests?|testing)/|(^|/)test_[^/]*$|_test\\.py$|conftest\\.py$' "
            "| xargs -r git add -N -- 2>/dev/null; "
            "git diff -- . ':(exclude)tests' ':(exclude)test' ':(exclude)testing' "
            "':(exclude,glob)**/test_*' ':(exclude,glob)**/conftest.py' ':(exclude,glob)**/*_test.py'"
        )
        return out.get("output", "")
