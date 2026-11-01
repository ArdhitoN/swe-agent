# Time log

Approximate time spent, and what was cut to fit.

| Phase | Time | What |
|---|---|---|
| Research and planning | ~2 h (the day before) | What makes the comparison fair; choice of model (cost, a fixed snapshot, room to improve); a fair rule for choosing bugs; the budget |
| Setup | ~30 min | Repo, environment, Docker, API key, issues |
| Bug selection and image checks | ~30 min | Pinned leaderboard snapshot, one-time seeded draw; image sizes (~4 GB each) and leak checks |
| Baseline runner and grading | ~45 min | mini-swe-agent through its own runner; official grader; a litellm crash fixed by adding the `mcp` dependency |
| Our agent, with 4 dev rounds | ~1.5 h | Tools, attempt loop with gates, recovery, test-based selection; 6 problems found and fixed on dev bugs |
| Test runs | ~2.5 h of compute | Baseline 40 runs; our agent 24; control 24; ablation 24. Mostly waiting: emulation and the flex tier are slow |
| Write-up | ~45 min | README, design doc, this log |

**Total:** about 1 working day, plus the planning the day before.

## What was cut to fit 1 day

- **Dev tuning:** 4 short rounds on 3 of the 6 dev bugs. The other 3 dev bugs were never used.
- **Runs:** 3 runs of our agent per bug (5 for the baseline). More runs would narrow the confidence intervals.
- **Grading every attempt:** we didn't grade each attempt separately, so we can't say how often a correct patch existed but wasn't picked.
- **An AI judge for ties:** not built; the selector is test-only.
- **A second machine:** everything ran on one arm64 Mac under x86 emulation; no cloud machine.
- **No retuning after seeing test results**, on purpose. Ideas the test results suggested (section 5 of `DESIGN.md`) are listed as next steps, to be checked on new bugs.
