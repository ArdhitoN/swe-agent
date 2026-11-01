# swe-agent

A coding agent that tries to fix **more real GitHub bugs** than the reference
agent, **mini-swe-agent**, using **the same model and the same budget**. We then
check that the improvement is real: not noise, not just extra compute, not memorization.

> Not to be confused with [SWE-agent](https://github.com/SWE-agent/SWE-agent). This repo
> uses mini-swe-agent (from the same team) as the *baseline* it must beat.

**Status:** in progress. Results, exact commands and the headline lift will be added when the runs finish.

## Where things are

| Path | What |
|---|---|
| `configs/experiment.yaml` | Every locked setting: model, budget, runs, seeds |
| `src/gated_agent/` | **The agent being tested** |
| `src/lift_eval/` | **The measuring setup**: same code for the baseline and our agent |
| GitHub issues | One per initiative; every PR links to at least one |

## Setup

```bash
make setup     # Python 3.11 venv + pinned dependencies (needs uv)
make test      # unit tests
make help      # all targets
```

The OpenAI key is read from `~/.config/test-gated-swe-agent/.env` (a line
`OPENAI_API_KEY=...`), or from the file named in `SWE_AGENT_ENV_FILE`. It is never stored in the repo.
