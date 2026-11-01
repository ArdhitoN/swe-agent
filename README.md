# swe-agent

A coding agent that tries to fix **more real GitHub bugs** than the reference agent,
**mini-swe-agent**, using **the same model and the same budget**. We then check that the improvement
is real: not noise, not just extra compute, not memorization.

> Not to be confused with [SWE-agent](https://github.com/SWE-agent/SWE-agent). This repo uses
> mini-swe-agent (from the same team) as the *baseline* it must beat.

## Result

**No meaningful lift.** On 8 SWE-bench Verified bugs, with the same model and the same per-bug budget:

| Agent | Resolved | Bugs resolved per run (of 8) | Runs | Cost per bug run |
|---|---|---|---|---|
| **A: Baseline** (mini-swe-agent, unmodified) | 57.5% | 4.60 | 5 | $0.009 |
| **B: Our agent** | **58.3%** | 4.67 | 3 | $0.048 |
| C: Control (our selector over 3 baseline patches) | 66.7% | 5.33 | 3 | $0.021 extra, plus 3 baseline runs |
| D: Ablation (our first attempt only) | 54.2% | 4.33 | 3 | none extra |

- **Lift of our agent over the baseline: +0.8 points** (+0.07 bugs of 8), 95% interval **[−27.5, +30.0]**.
- Every comparison's interval includes zero, so 8 bugs can't separate these agents. The directions agree, though:
  - one attempt of ours is **not** better than one baseline run (−3.3 points);
  - test-based selection helps wherever it's applied (+4.2 on our attempts, +9.2 on the baseline's patches);
  - the best combination was **the baseline's patches plus our selector**.
- **Why our agent didn't win:** every patch it chose had passed its own checks (reproduction passes, no
  new failures in related tests), but 10 of 24 were wrong by the official tests. It tended to make narrow
  fixes that satisfied its own reproduction but not the general behaviour the maintainers' tests expect.
  Details: [`DESIGN.md`](DESIGN.md), section 5.
- **Memorization:** the strongest check (can the model write the fix from the task ID alone?) found nothing
  for any bug. A weaker check flags all 8 as "suspect" ([`reports/contamination.md`](reports/contamination.md)).
- **Leaks:** 0 commands that could reveal the fix, in 182 trajectories ([`reports/leak_scan.md`](reports/leak_scan.md)).
- **Total API spend: $2.56**, including all development runs.

Full tables: [`reports/summary.md`](reports/summary.md). How and why everything was built:
[`DESIGN.md`](DESIGN.md).

## What was compared

| | Agent | What it is |
|---|---|---|
| **A** | **Baseline** | mini-swe-agent 2.4.6, **unmodified**, through its own SWE-bench runner and config |
| **B** | **Our agent** | up to 3 attempts in one shared budget; each attempt finds the code, writes a reproduction that must fail on the original code, fixes, and may only submit after its tests pass; then the final patch is picked with tests |
| **C** | Control | **our** test-based selector applied to 3 of the **baseline's** patches. If C does as well as B, our gain is just "more tries + picking" |
| **D** | Ablation | our agent's **first attempt only**: is one attempt of ours better than one baseline run? |

Same for every agent:
- **Model:** `gpt-5-mini-2025-08-07` (a dated snapshot), OpenAI "flex" tier.
- **Budget per bug:** the baseline's own limits, **250 model calls and $3**. Our agent's attempts share it.
- **Bugs:** the same 8 SWE-bench Verified bugs.
- **Grader:** the official SWE-bench harness.
- **Machine:** one arm64 Mac running the x86 images under Docker emulation.

**Runs:** baseline 5 per bug; our agent 3 per bug; control 3 per bug (built from the baseline's
patches); ablation 3 per bug (built from our runs).

**The 8 bugs** were drawn once, with a seed, from the middle-difficulty band of SWE-bench Verified
Mini: bugs fixed by 10–86% of public mini-swe-agent runs, excluding our own model's runs. The rule and
seed were committed before the draw ([`reports/task_selection.md`](reports/task_selection.md)).
**Because easy and near-impossible bugs were removed on purpose, these percentages are not comparable
to full-benchmark scores.**

## Run it

Needs [uv](https://docs.astral.sh/uv/), Docker, and an OpenAI API key in
`~/.config/test-gated-swe-agent/.env` as a line `OPENAI_API_KEY=...` (or set `SWE_AGENT_ENV_FILE`
to another file). Any litellm-compatible endpoint works: change `model.name` in
`configs/experiment.yaml`.

```bash
make setup          # Python 3.11 venv + pinned dependencies
make test           # unit tests

make report         # rebuild every table from the saved logs (no API key, no Docker)

make select-tasks   # the one-time bug draw (rerunning gives the same bugs)
make baseline       # A: mini-swe-agent, 5 runs per bug
make ours           # B: our agent, 3 runs per bug
make control        # C: our selector over baseline patches
make ablation       # D: our first attempt only
make contamination  # memorization checks
make leak-scan      # scan every trajectory for commands that could reveal the fix
make all            # everything above, in order
```

Each SWE-bench image is ~4 GB, so the runners download, use and delete images **one bug at a time**.
Everything that was run is saved under `results/`: every patch, every trajectory, and the grader's
test output for every run.

## Where things are

| Path | What |
|---|---|
| `src/gated_agent/` | **The agent being tested**: tools, attempt loop, recovery, patch selection |
| `src/lift_eval/` | **The measuring setup**, the same for every agent: bug selection, runners, grading, statistics, memorization checks, leak scan |
| `configs/experiment.yaml` | Every setting, each with a comment saying why |
| `configs/baseline_mini.yaml` | The exact mini-swe-agent config used (unmodified) |
| `results/<agent>/run_<k>/<bug>/` | Patch (`preds.json`), trajectories, cost, grader output (`grade/`) |
| `reports/` | Results, bug selection, memorization checks, leak scan, image checks |
| `DESIGN.md` | Architecture, every decision with its reasoning, what didn't work, limitations, next steps |
| `NOTES.md` | Environment facts (image sizes, leak checks on the images) |
| `TIME_LOG.md` | Time spent and what was cut |

## Credits

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) (baseline; its model client and Docker environment are reused)
- [SWE-bench](https://github.com/SWE-bench/SWE-bench) (dataset and official grader), [SWE-bench Verified Mini](https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini)
- Public per-bug results from the [SWE-bench experiments repo](https://github.com/SWE-bench/experiments) (used only to choose bugs)
- [litellm](https://github.com/BerriAI/litellm)
- Ideas: [SWE-agent](https://arxiv.org/abs/2405.15793) (guarded edit tool), [Agentless](https://arxiv.org/abs/2407.01489) and [CodeMonkeys](https://scalingintelligence.stanford.edu/blogs/codemonkeys) (reproduction tests and test-based selection), [The SWE-Bench Illusion](https://arxiv.org/abs/2506.12286) and [OpenAI's SWE-bench Verified audit](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) (memorization checks), [SWE-smith](https://arxiv.org/abs/2504.21798) (loop behaviour)
