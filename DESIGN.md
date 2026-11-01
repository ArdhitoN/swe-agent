# Design

This document explains what was built, how it works, why each decision was made, what didn't
work, and what we'd do next. Results are in `reports/summary.md`; how to rerun everything is in
the README.

## 1. The question

Can a better **harness** (the code around a language model: tools, workflow, checks) make the
**same model** fix more real GitHub bugs than the standard reference agent, within the **same budget**?
And can we show the improvement is real: not noise, not just extra compute, not memorization?

- **Reference agent (the baseline):** [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
  2.4.6, unmodified. It gives the model a single `bash` tool and a fixed prompt.
- **Bugs:** 8 real issues from [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/),
  graded by the **official SWE-bench harness**: a bug counts as resolved only if the tests that should
  start passing pass, and the tests that already passed still pass.
- **Model:** `gpt-5-mini-2025-08-07`, the same for every agent.

## 2. Architecture

```
                       configs/experiment.yaml  (every setting, locked before test runs)
                                   │
          ┌────────────────────────┴─────────────────────────┐
          │                 lift_eval (measuring)             │
          │  bug selection → schedule (one bug at a time) →   │
          │  run agent → official grader → stats → report     │
          └───────┬───────────────────────────────┬──────────┘
                  │ same runner, grader, stats     │
        ┌─────────▼─────────┐            ┌─────────▼──────────────────────────────┐
        │ A: mini-swe-agent │            │ gated_agent (ours)                       │
        │ unmodified        │            │  per bug: up to 3 attempts, one budget    │
        └───────────────────┘            │   attempt: find → reproduce → fix →       │
                                         │            verify → submit (gated)        │
                                         │  then: test-based patch selection         │
                                         └──────────────────────────────────────────┘
```

Two packages, kept apart on purpose:
- **`gated_agent`** is what is being tested.
- **`lift_eval`** does the testing. The baseline and our agent go through the **same** runner,
  grader and statistics, so any difference comes from the agents.

### One attempt (`src/gated_agent/attempt.py`)

Built on mini-swe-agent's own `DefaultAgent`: the same loop, the same model client, the same
Docker environment, and the same trajectory files. The message history is append-only, which keeps
the provider's prompt cache working (cached input is ~10× cheaper). What we add:

1. **Typed tools** (`src/gated_agent/tools.py`, `toolbox/toolbox.py`):

   | Tool | What it does |
   |---|---|
   | `search` | search the code, short output |
   | `outline` | list a file's classes and functions |
   | `view` | numbered lines, max 150 |
   | `edit` | replace one exact, unique string; undone if the edit breaks syntax or imports (checked with the project's own Python); tolerates a constant indentation slip |
   | `run_tests` | the repo's own test runner |
   | `register_repro` | accept a reproduction only if it fails on the original code |
   | `verify` | reproduction passes and related tests have no new failures |
   | `submit` | refused unless `verify` passed on the current code |
   | `bash` | guarded |

2. **Gates, where tests decide instead of the model:**
   - A reproduction script (in `/tmp`, so it never enters the patch) is registered only if it
     **fails on the original code**.
   - `verify` passes only if the reproduction now **passes** and the related existing tests have
     **no new failures** compared with the original code.
   - `submit` is refused until `verify` has passed on exactly the current code.
3. **Recovery** (`recovery.py`). It detects a repeated call, repeated output, back-and-forth edits,
   and long stretches without progress, then escalates: nudge → roll back to the last good code →
   restart with a short automatic note.
4. **Guarded bash.** Other git history, the internet and package installs are refused, because
   they could reveal the fix.

### One bug (`src/gated_agent/agent.py`, `select/selector.py`)

- Up to 3 attempts in **one shared budget**: the baseline's own **250 calls and $3 per bug**.
  Unused budget rolls over to the next attempt.
- Each attempt starts in a fresh container with a different strategy hint ("minimal fix",
  "root cause first", "follow the failing path"). It stops early after two attempts verify on their own.
- **Selection**, no model calls:
  1. pool every attempt's reproduction, keeping those that fail on the original code;
  2. run each candidate against all of them plus the related existing tests;
  3. drop candidates with new failures;
  4. prefer more reproductions passed, then the biggest group with identical results, then the smallest patch.

## 3. How the comparison is kept fair

| Risk | What we did |
|---|---|
| Different model or settings | One dated model snapshot and one API tier ("flex", about half price) for every agent |
| Different budget | Our agent's attempts **together** get the baseline's own per-bug limits (250 calls, $3) |
| Weakened baseline | mini-swe-agent's own batch runner and own config, copied to `configs/baseline_mini.yaml` with its hash |
| Noise (one bug = 12.5 points) | 5 baseline runs and 3 runs of our agent per bug; per-bug success rates; bootstrap confidence intervals over bugs and runs |
| "It's just more tries" | **Control (C):** our same selector over 3 baseline patches |
| "One attempt isn't better" | **Ablation (D):** our first attempt alone, graded |
| Tuning on the test bugs | All tuning on 6 separate dev bugs; agent code frozen and tagged before the test runs |
| Leaks between bugs | Dev bugs share no files with test bugs' fixes (checked by script, file names only); fresh containers and folders per run; no cross-bug memory |
| Leaks from the environment | Images checked: no git history after the bug. The containers do have internet access, so our agent blocks network commands, and every trajectory of every agent is scanned (`reports/leak_scan.md`) |
| Memorization | Four checks per bug with thresholds fixed in advance (`reports/contamination.md`) |
| Cherry-picked bugs | A written rule and seed committed before a one-time draw (`reports/task_selection.md`) |

## 4. Decisions and why

Each decision: **why**, what was **rejected**, and the **trade-off** we accept.

**Model: `gpt-5-mini-2025-08-07`.**
- **Why:** cheap (about $0.009 per baseline bug run at the flex tier); a dated snapshot, so it can't
  change between runs; and mid-level on these bugs (public runs fix 55–68% of our band), which leaves
  room to improve.
- **Rejected:**
  - GPT-5 nano: fixed only 5% of the band in public runs, and costs more per bug because it takes more steps.
  - DeepSeek V3.2: no longer served by DeepSeek's API, whose old model names now redirect to a newer model, so it can't be pinned.
  - Kimi, GLM, Qwen: 2.5–5× the price.
  - MiniMax M2.5: too strong to leave room.
- **Trade-off:** a closed model; mitigated by the snapshot and fully saved logs.

**"Flex" API tier for every agent.**
- **Why:** about half price, same model, so the comparison is unaffected.
- **Rejected:** the batch API, because an agent needs an answer at every step.
- **Trade-off:** slower responses.

**Bugs: a seeded draw from the middle-difficulty band of SWE-bench Verified Mini.**
- **Why:** with 8 slots, a bug every agent fixes (or none does) adds nothing to a comparison. The rule
  keeps bugs fixed by 10–86% of 36 public mini-swe-agent runs, **excluding our own model's runs**,
  then draws 4 Django + 4 Sphinx bugs with a seed written down beforehand. The rule, seed and data were
  committed before the draw, and the draw ran once.
- **Rejected:** a purely random 8 (about half the slots wasted); picking bugs the baseline failed
  (cherry-picking, and since results vary run to run it would create fake improvement).
- **Trade-off:** percentages on this band are **not comparable** to full-benchmark scores. The band
  edges sit at natural gaps in the data and were chosen after looking at the public distribution, but
  before running our model and without its results.

**Baseline unmodified, through its own runner.**
- **Why:** any change we made could weaken it.
- **Rejected:** the heavier SWE-agent as the reference.
- **Trade-off:** none worth noting.

**Same budget = the baseline's own limits, shared by all our attempts.**
- **Why:** "same budget" is then defined by the reference, not by us.
- **Trade-off:** the baseline usually spends far less than its cap, so the actual spend of every
  agent is reported, and the control measures the "more tries" effect directly.

**3 attempts, early stop after two verified ones.**
- **Why:** the first few attempts add the most; 3 is the smallest number where a majority vote can
  break a tie; and it fits the budget.
- **Trade-off:** less benefit than large-scale sampling would give.

**Deterministic, test-based selection (no AI judge).**
- **Why:** reproducible, free, and easy to explain.
- **Rejected:** an AI judge, which costs budget and adds randomness (listed as future work).

**Tests decide, not the model.**
- **Why:** models often say "fixed" when it isn't, and running code is an objective check.
- **Trade-off:** test runs take time and steps.

**Guarded edit tool.**
- **Why:** SWE-agent found its linted edit command was the most important part of its interface
  ([paper](https://arxiv.org/abs/2405.15793)). mini-swe-agent edits with shell commands, which can
  silently break files.

**One bug at a time on the Docker side.**
- **Why:** each SWE-bench image is ~4 GB with almost nothing shared, and this machine has ~17 GB free.
  Images are downloaded, used and deleted per bug.

**Everything on one machine** (an arm64 Mac, running the x86 images under emulation).
- **Why:** all agents share one machine, so hardware can't explain a difference.
- **Trade-off:** slower.

**Development on 6 dev bugs only; code freeze before test runs.**
- **Why:** tuning on the test bugs would be overfitting. The git tag shows the agent didn't change
  after the freeze.

## 5. Results, and why our agent didn't win

| Agent | Resolved | Runs | Cost per bug run |
|---|---|---|---|
| A: Baseline | 57.5% | 5 | $0.009 |
| B: Our agent | 58.3% | 3 | $0.048 |
| C: Control (our selector over baseline patches) | 66.7% | 3 | $0.021 extra + 3 baseline runs |
| D: Ablation (our first attempt) | 54.2% | 3 | — |

**The lift is +0.8 points, 95% interval [−27.5, +30.0]: no meaningful difference.** The full tables
are in `reports/summary.md`.

**What the comparisons say** (all intervals include zero, so these are directions, not proof):
- **Our single attempt is not better than one baseline run** (D − A = −3.3 points). The typed tools,
  gates and recovery didn't make one attempt better.
- **Test-based selection helps wherever it's applied:** +4.2 points over our own attempts (B − D), and
  +9.2 over the baseline's (C − A).
- **The best combination was the baseline's patches plus our selector** (C). For example, on
  `sphinx-doc__sphinx-8056` the control picked a correct baseline patch in 3/3 runs, while the baseline
  alone got 2/5 and our agent 0/3.

**Why our agent didn't win:**
1. **Our own checks were a poor stand-in for the official tests.** Every patch our agent chose had
   passed them (its reproduction passes, no new failures in related tests), but **10 of 24 were wrong**.
   A reproduction checks the case the agent understood, which may not be what the maintainers meant.
2. **It tended to make narrow fixes.** On `django__django-11815` it serialized enums by name only for
   lazily translated values, which is the case in its own reproduction. The official tests expect all
   enums serialized by name, and the baseline's resolved patches did that. Three of our design choices
   push toward narrow fixes:
   - the "minimal fix" strategy hint;
   - "keep the change small" in the prompt;
   - "smallest patch wins" as the last tie-break in selection.
3. **It's ~5.5× more expensive per bug run** (63 calls vs 18 on average). That's inside the shared
   budget, but the extra work didn't buy accuracy here.

These lessons come from the **test** bugs, so the agent was **not** retuned on them: that would be
overfitting to these 8 bugs. They are next steps (section 8), to be checked on new bugs.

## 6. What didn't work during development, and what we changed (all found on dev bugs)

| Problem | Where | Change |
|---|---|---|
| litellm 1.106 crashed on every request with tools (missing `mcp` package) | first baseline smoke test, $0 spent | `mcp` added as a dependency; environment only, the same for both agents |
| The regression check ran unrelated tests (`model_enums` for a change to `deletion.py`) | dev bug `django__django-11885` | match by package first, then file name, with shared word stems ("deletion" ↔ "delete") |
| The stuck detector fired on progress: re-registering an edited reproduction; our own rollback looked like back-and-forth edits; "15 idle steps" during normal reading | same bug, 2 of 3 attempts restarted | edits reset the repeat history; rollbacks reset the code history; the idle check waits until reading is over |
| Most edits failed on indentation; one attempt used its whole share without verifying | dev bug `sphinx-doc__sphinx-9230` | edit applies a constant indentation shift and says so; otherwise shows the exact text |
| All three attempts fixed the wrong component, because their reproductions called a guessed internal function | same bug | prompt: reproduce exactly as the issue describes (same input, same entry point) |
| Our selector rejected a baseline patch the grader would accept (only tried `git apply`) | control on the same bug | use the grader's own fallbacks (`--3way`, `patch --fuzz`) |

Selection can't fix wrong **localization**: if every attempt looks in the wrong place, there is
nothing good to pick.

## 7. Limitations

- **8 bugs is a small sample.** One bug is 12.5 points; the lift's 95% interval spans about 57 points.
- **The band changes what the percentages mean** (see the bug-selection decision above).
- **Memorization checks are imperfect.** "Right file from the issue alone" fired for all 8 bugs,
  but these issue texts name the class or feature involved, so it says little here. The stronger
  check, "fix from the task ID alone", found nothing for any bug. Without a comparison on repos
  outside SWE-bench, we can't fully separate knowledge of the codebase from memory.
- **The regression check is a heuristic.** It picks related test folders or files by name and runs
  only those, so a regression elsewhere can be missed.
- **Emulation:** x86 images on an arm64 Mac; slower, and timing-sensitive tests could behave differently.
- **One model.** The lift may differ for stronger or weaker models.

## 8. Next steps

1. **Use the selector as an add-on to the baseline.** The control (baseline patches + our selector) was
   the best combination. It's also cheap: the patches come from a cheap agent, and only the
   reproductions need extra calls.
2. **Stop pushing toward narrow fixes:** drop the "minimal fix" hint and "keep the change small"; break
   ties toward patches that pass *more* reproductions written independently (each attempt's script tests
   a different reading of the issue), not toward the smallest patch.
3. **Better reproductions:** ask for several scripts per attempt that cover the general behaviour the
   issue implies, not only the reported case.
4. **More bugs and more runs**, to narrow the intervals. Changes 1–3 must be judged on **new** bugs, not
   these 8.
5. **Better localization** for bugs where every attempt looks in the wrong place.
6. **An AI judge for ties**, compared against the deterministic selector on dev bugs.
7. **Memorization control** on repos outside SWE-bench (e.g. SWE-bench Pro or freshly collected issues).
8. **Grade every attempt**, to measure how often a correct patch existed but wasn't picked.
