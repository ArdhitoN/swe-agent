# One command per step, and `make all` for everything. Run `make help` to list them.
PY ?= .venv/bin/python
LIFT = $(PY) -m lift_eval.cli

.PHONY: help setup test select-tasks check-images baseline ours control ablation grade contamination leak-scan report all

help:           ## List targets
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/\t/'

setup:          ## Create .venv and install pinned dependencies
	uv venv --python 3.11 .venv
	uv pip install --python $(PY) -r requirements.lock -e '.[dev]'

test:           ## Run unit tests
	$(PY) -m pytest -q

select-tasks:   ## One-time seeded draw of test + dev bugs (#2)
	$(LIFT) select-tasks

check-images:   ## Pull images; check emulation, future git history, network (#3)
	$(LIFT) check-images

baseline:       ## Arm A: unmodified mini-swe-agent, all runs (#4)
	$(LIFT) run-baseline

ours:           ## Arm B: our agent, all runs (#8)
	$(LIFT) run-ours

control:        ## Arm C: our selector over Arm A's patches (#8)
	$(LIFT) run-control

ablation:       ## Arm D: first attempt of each Arm B run (#8)
	$(LIFT) run-ablation

grade:          ## Official SWE-bench harness on every run (#4)
	$(LIFT) grade-all

contamination:  ## Memorization probes P1-P4 (#9)
	$(LIFT) contamination

leak-scan:      ## Scan all trajectories for leak commands (#9)
	$(LIFT) leak-scan

report:         ## Tables + confidence intervals from saved results; no API key needed (#10)
	$(LIFT) report

all: select-tasks check-images baseline ours control ablation grade contamination leak-scan report  ## Everything, in order
