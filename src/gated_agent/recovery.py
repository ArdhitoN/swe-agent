"""Notice when an attempt is stuck, and escalate: nudge -> roll back -> restart.

The cheapest fix comes first. Expectation (from published agent studies): loop handling mostly saves
budget for other attempts; on its own it rarely turns a failure into a success.
"""

import hashlib
import json
from collections import deque

NUDGE, ROLLBACK, RESTART = 1, 2, 3


def _key(tool: str, args: dict) -> str:
    return tool + ":" + json.dumps(args, sort_keys=True)[:4000]


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


class StuckDetector:
    def __init__(self, window: int = 10, repeats: int = 3, idle_steps: int = 15):
        self.window = window
        self.repeats = repeats
        self.idle_steps = idle_steps
        self.actions: deque[str] = deque(maxlen=window)
        self.outputs: deque[str] = deque(maxlen=repeats)
        self.diff_history: list[str] = []
        self.steps_since_progress = 0
        self.level = 0

    def record(self, tool: str, args: dict, output: str, diff: str, progress: bool, changed_files: bool = False) -> None:
        """progress = an edit, a test run, a registered reproduction or a verify call.

        changed_files = a file was successfully edited or created (repo or /tmp). Repeating a call
        after changing a file is not a loop (e.g. editing the reproduction, then registering it again),
        so the repeat history starts over.
        """
        if changed_files:
            self.actions.clear()
            self.outputs.clear()
        self.actions.append(_key(tool, args))
        self.outputs.append(_digest(output))
        digest = _digest(diff)
        if not self.diff_history or self.diff_history[-1] != digest:
            self.diff_history.append(digest)
        self.steps_since_progress = 0 if progress else self.steps_since_progress + 1

    def forget_code_history(self) -> None:
        """After a rollback the code jumps back on purpose; that must not look like back-and-forth edits."""
        self.diff_history = self.diff_history[-1:]

    def reason(self, exploring: bool = False) -> str | None:
        """exploring = still in the reading phase, where many steps without edits are normal."""
        if self.actions:
            last = self.actions[-1]
            if sum(a == last for a in self.actions) >= self.repeats:
                return "the same tool call repeated"
        if len(self.outputs) == self.repeats and len(set(self.outputs)) == 1:
            return "the same output several times in a row"
        h = self.diff_history
        if len(h) >= 3 and h[-1] == h[-3] and h[-1] != h[-2]:
            return "switching back and forth between the same two versions of the code"
        if not exploring and self.steps_since_progress >= self.idle_steps:
            return f"{self.steps_since_progress} steps without editing, testing or verifying"
        return None

    def escalate(self) -> int:
        """Call when reason() fires. Returns the new level and resets the short-term memory."""
        self.level = min(self.level + 1, RESTART)
        self.actions.clear()
        self.outputs.clear()
        self.steps_since_progress = 0
        return self.level
