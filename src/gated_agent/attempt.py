"""One attempt at one bug: find the code, reproduce, fix, verify, then submit.

Built on mini-swe-agent's DefaultAgent, so the loop, message history (append-only, which keeps the
prompt cache working) and trajectory files are the same as the baseline's. What we add:
- typed tools instead of bash only,
- gates: a reproduction must fail on the original code, and `submit` is refused until `verify`
  has passed on the current code,
- recovery when the attempt is stuck.
"""

import hashlib
import shlex

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.exceptions import InterruptAgentFlow, LimitsExceeded, Submitted

from gated_agent import prompts
from gated_agent.recovery import NUDGE, RESTART, ROLLBACK, StuckDetector
from gated_agent.tools import ToolRunner, blocked_reason

MAX_OBSERVATION = 8000
PROGRESS_TOOLS = {"edit", "create", "run_tests", "register_repro", "verify"}
SETUP_ERRORS = ("SyntaxError", "IndentationError", "ImproperlyConfigured", "AppRegistryNotReady")


class Restart(InterruptAgentFlow):
    """The attempt gave up after escalating; the next attempt gets a short note about it."""


class GatedAgentConfig(AgentConfig):
    system_template: str = prompts.SYSTEM
    instance_template: str = prompts.INSTANCE
    localize_share: float = 0.25
    mode: str = "fix"  # "fix", or "repro" to only write a reproduction (used for the control comparison)


def _shorten(text: str, limit: int = MAX_OBSERVATION) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... [{len(text) - limit} characters omitted] ...\n{text[-half:]}"


def _exit(status: str, submission: str, **extra) -> dict:
    return {"role": "exit", "content": status, "extra": {"exit_status": status, "submission": submission, **extra}}


class GatedAgent(DefaultAgent):
    def __init__(self, model, env, **kwargs):
        super().__init__(model, env, config_class=GatedAgentConfig, **kwargs)
        self.tools = ToolRunner(env)
        self.detector = StuckDetector()
        self.repro_path: str | None = None
        self.repro_code: str | None = None
        self.verified_diff: str | None = None
        self.last_verify: dict = {}
        self.checkpoint = ""  # last diff that passed the syntax/import checks
        self.events: list[dict] = []  # gates and recovery actions, saved with the trajectory
        self.nudged_localize = False

    # ------------------------------------------------------------ limits

    def query(self) -> dict:
        cfg = self.config
        if 0 < cfg.step_limit <= self.n_calls or 0 < cfg.cost_limit <= self.cost:
            # Out of budget: hand over whatever we have (marked unverified) instead of nothing.
            raise LimitsExceeded(_exit("LimitsExceeded", self._current_patch(), verified=False))
        if (
            cfg.mode == "fix"
            and not self.nudged_localize
            and self.repro_path is None
            and self.n_calls >= int(cfg.step_limit * cfg.localize_share)
        ):
            self.nudged_localize = True
            self.events.append({"step": self.n_calls, "event": "nudge_localize"})
            self.add_messages({"role": "user", "content": prompts.NUDGE_LOCALIZE})
        return super().query()

    # ------------------------------------------------------------ tools

    def execute_actions(self, message: dict) -> list[dict]:
        outputs = []
        for action in message.get("extra", {}).get("actions", []):
            text = self._dispatch(action)
            outputs.append({"output": _shorten(text), "returncode": 0, "exception_info": ""})
            diff = self._current_patch()
            changed = action["tool"] in ("edit", "create") and text.startswith(("edited", "created"))
            self.detector.record(action["tool"], action["args"], text, diff, action["tool"] in PROGRESS_TOOLS, changed)
        observations = self.model.format_observation_messages(message, outputs, self.get_template_vars())
        added = self.add_messages(*observations)
        return added + self._maybe_recover()

    def _dispatch(self, action: dict) -> str:
        tool, args = action["tool"], action["args"]
        try:
            handler = getattr(self, f"_tool_{tool}", None)
            if handler:
                return handler(**args)
            timeout = 900 if tool == "run_tests" else 180
            text, data = self.tools.call(tool, args, timeout=timeout)
            if tool in ("edit", "create") and data.get("ok"):
                self.checkpoint = self._current_patch()
            return text
        except TypeError as e:
            return f"bad arguments for {tool}: {e}"

    def _tool_bash(self, command: str = "", **_) -> str:
        if reason := blocked_reason(command):
            self.events.append({"step": self.n_calls, "event": "blocked", "command": command[:300], "reason": reason})
            return f"refused: {reason} is not allowed here."
        before = self._current_patch()
        out = self.env.execute({"command": command})
        text = f"exit code {out['returncode']}\n{out.get('exception_info') or ''}{out.get('output', '')}"
        after = self._current_patch()
        if after != before and not self._compiles():
            self._rollback("a shell command left the code unable to compile")
            text += "\n[the shell command broke the code; your source files were restored to the last good state]"
        return text

    def _tool_register_repro(self, path: str = "", **_) -> str:
        if not path.startswith("/tmp/"):
            return "put the reproduction script under /tmp/ so it never becomes part of the patch."
        code = self.tools.sh(f"cat {shlex.quote(path)}")
        if code["returncode"] != 0:
            return f"cannot read {path}: {code['output'][-300:]}"
        text, data = self._on_original(lambda: self.tools.call("run_script", {"path": path}))
        if data.get("exit_code", 0) == 0:
            return "not registered: the script exits 0 on the ORIGINAL code, so it doesn't show the bug.\n" + text
        if any(err in text for err in SETUP_ERRORS):
            return "not registered: the script fails because of a setup error, not because of the bug.\n" + text
        self.repro_path, self.repro_code = path, code["output"]
        self.events.append({"step": self.n_calls, "event": "repro_registered", "path": path})
        if self.config.mode == "repro":
            raise Submitted(_exit("Submitted", self.repro_code, verified=True))
        return "registered: the script fails on the original code, as it should.\n" + text

    def _tool_verify(self, **_) -> str:
        patch = self._current_patch()
        if not self.repro_path:
            return "verify failed: register a reproduction first (`register_repro`)."
        if not patch.strip():
            return "verify failed: no source changes yet."
        repro_text, repro = self.tools.call("run_script", {"path": self.repro_path})
        reg_text, reg = self.tools.call("regression_check", {}, timeout=2400)
        ok = repro.get("exit_code") == 0 and reg.get("ok", False)
        self.last_verify = {"ok": ok, "repro_exit": repro.get("exit_code"), "regressions": reg.get("regressions", []),
                            "targets": reg.get("targets", []), "step": self.n_calls}
        self.events.append({"event": "verify", **self.last_verify})
        self.verified_diff = patch if ok else None
        verdict = "VERIFY PASSED. You may now `submit`." if ok else "VERIFY FAILED. Fix the problem and verify again."
        return f"{verdict}\n\n[reproduction] {repro_text}\n\n[regression check] {reg_text}"

    def _tool_submit(self, **_) -> str:
        patch = self._current_patch()
        if self.verified_diff is not None and patch == self.verified_diff:
            raise Submitted(_exit("Submitted", patch, verified=True))
        reason = "no successful `verify` yet" if self.verified_diff is None else "the code changed after `verify`"
        return f"submit refused: {reason}. Run `verify` first."

    # ------------------------------------------------------------ recovery

    def _maybe_recover(self) -> list[dict]:
        exploring = self.repro_path is None and self.n_calls < int(self.config.step_limit * self.config.localize_share)
        reason = self.detector.reason(exploring=exploring)
        if not reason:
            return []
        level = self.detector.escalate()
        self.events.append({"step": self.n_calls, "event": "stuck", "reason": reason, "level": level})
        if level == NUDGE:
            return self.add_messages({"role": "user", "content": prompts.NUDGE_REPEAT.format(reason=reason)})
        if level == ROLLBACK:
            self._rollback(reason)
            return self.add_messages({"role": "user", "content": (
                prompts.NUDGE_REPEAT.format(reason=reason)
                + " Your source files were reset to the last version that passed the syntax checks."
            )})
        lessons = self._lessons(reason)
        raise Restart(_exit("Restart", self._current_patch(), verified=False, lessons=lessons))

    def _rollback(self, reason: str) -> None:
        self.tools.sh("cd /testbed && git stash push --include-untracked -q && git stash drop -q")
        if self.checkpoint.strip():
            self.tools.sh(f"cd /testbed && echo {shlex.quote(self.checkpoint)} | git apply --whitespace=nowarn -")
        self.detector.forget_code_history()
        self.events.append({"step": self.n_calls, "event": "rollback", "reason": reason})

    def _lessons(self, reason: str) -> str:
        """A short, automatic note for the next attempt (no extra model call)."""
        touched = sorted({line[6:] for line in self.checkpoint.splitlines() if line.startswith("+++ b/")})
        notes = [f"- The previous attempt got stuck: {reason}."]
        if touched:
            notes.append(f"- It edited: {', '.join(touched)}.")
        if self.last_verify and not self.last_verify.get("ok"):
            notes.append(f"- Its last verify failed (reproduction exit {self.last_verify.get('repro_exit')}, "
                         f"new test failures: {len(self.last_verify.get('regressions', []))}).")
        if not self.repro_path:
            notes.append("- It never registered a working reproduction.")
        return "\n".join(notes)

    # ------------------------------------------------------------ helpers

    def _current_patch(self) -> str:
        return self.tools.source_diff()

    def _compiles(self) -> bool:
        out = self.tools.sh(
            "cd /testbed && files=$(git diff --name-only -- '*.py'; git ls-files --others --exclude-standard -- '*.py'); "
            "[ -z \"$files\" ] || /opt/miniconda3/envs/testbed/bin/python -m py_compile $files"
        )
        return out["returncode"] == 0

    def _on_original(self, fn):
        """Run fn with the agent's source changes temporarily removed."""
        stashed = bool(self._current_patch().strip())
        if stashed:
            self.tools.sh("cd /testbed && git stash push --include-untracked -q")
        try:
            return fn()
        finally:
            if stashed:
                self.tools.sh("cd /testbed && git stash pop -q")

    def serialize(self, *extra_dicts) -> dict:
        data = super().serialize(*extra_dicts)
        data["info"]["gated"] = {
            "events": self.events,
            "repro_path": self.repro_path,
            "repro_code": self.repro_code,
            "verified": self.verified_diff is not None,
            "last_verify": self.last_verify,
        }
        return data


def patch_id(patch: str) -> str:
    return hashlib.sha1(" ".join(patch.split()).encode()).hexdigest()[:12]
