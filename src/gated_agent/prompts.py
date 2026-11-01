"""Prompts for our agent. They are generic: no repo-, file- or bug-specific hints."""

SYSTEM = (
    "You are a careful software engineer fixing a real bug in an open-source Python project. "
    "You work through tools. Think briefly, then call tools. Be efficient: every call costs budget."
)

INSTANCE = """<issue>
{{task}}
</issue>

Fix this issue in the repository at /testbed by changing non-test source files.

## How to work (tests decide when you're done, not you)
1. **Find the code.** Use `search`, `outline` and `view` to locate where the behaviour comes from.
   Don't read files at random: search for names and messages from the issue.
2. **Reproduce the bug.** Write a small standalone script under /tmp (for example /tmp/repro.py) that
   exits with a NON-ZERO code while the bug is present and exits 0 once it is fixed (use `assert`
   or `sys.exit(1)`). For Django, configure settings inside the script
   (`settings.configure(...)` then `django.setup()`). Then call `register_repro` with its path.
   It is run against the original code and must fail there.
   **Reproduce the behaviour exactly as the issue describes it**: the same input and the same entry point
   the user used (the same directive, field, API call or command), not an internal function you guessed.
   A script that calls the wrong function can "pass" while the real bug remains.
3. **Fix it** with `edit` (one unique exact replacement per call). Keep the change small and general,
   consistent with the surrounding code. Never edit tests.
4. **Check it** with `verify`: your reproduction must pass and related existing tests must not break.
   If it fails, read the output, fix, and verify again.
5. **Submit** with `submit` right after a successful `verify`.

## Rules
- No internet, no package installs, no git history beyond the current commit. Such commands are refused.
- Command output is shortened; ask for specific line ranges instead of whole files.
- Budget for this attempt: about {{step_limit}} tool-using replies.

## Approach for this attempt
{{strategy_hint}}
{% if lessons %}
## Notes from a previous attempt on this same issue
{{lessons}}
{% endif %}"""

# One hint per attempt, rotated. Identical attempts tend to repeat identical mistakes.
STRATEGY_HINTS = [
    "Aim for the minimal fix at the most likely location named or implied by the issue.",
    "Find the root cause first: look at the callers and related functions before editing.",
    "Start from your reproduction and follow the failing code path step by step.",
    "Consider whether the issue implies a more general fix than the single reported case.",
]

REPRO_ONLY_INSTANCE = """<issue>
{{task}}
</issue>

Your only job: write a standalone script under /tmp (for example /tmp/repro.py) that reproduces this
issue in /testbed. It must exit with a NON-ZERO code while the bug is present and exit 0 once the bug is
fixed (use `assert` or `sys.exit(1)`). For Django, configure settings inside the script
(`settings.configure(...)` then `django.setup()`). Do not change any repository files.
Reproduce the behaviour exactly as the issue describes it: the same input and the same entry point the user
used (the same directive, field, API call or command), not an internal function you guessed.
When the script fails on the current code because of the bug, call `register_repro` with its path.
Budget: about {{step_limit}} tool-using replies."""

NUDGE_LOCALIZE = (
    "You have used a quarter of this attempt's budget without registering a reproduction. "
    "Move on: write the reproduction script now and call `register_repro`."
)
NUDGE_REPEAT = (
    "You are repeating the same action without progress ({reason}). Stop and try a different approach: "
    "re-read the issue, check a different part of the code, or change your reproduction."
)
