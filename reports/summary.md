# Results

8 test bugs. Each cell: in how many runs the bug was resolved.

| Bug | A | B | C | D | Memorization check |
|---|---|---|---|---|---|
| `django__django-11790` | 0/5 | 0/3 | 0/3 | 0/3 | suspect |
| `django__django-11815` | 3/5 | 0/3 | 1/3 | 0/3 | suspect |
| `django__django-12193` | 0/5 | 2/3 | 0/3 | 1/3 | suspect |
| `django__django-12774` | 5/5 | 3/3 | 3/3 | 3/3 | suspect |
| `sphinx-doc__sphinx-10323` | 5/5 | 3/3 | 3/3 | 3/3 | suspect |
| `sphinx-doc__sphinx-7757` | 3/5 | 3/3 | 3/3 | 3/3 | suspect |
| `sphinx-doc__sphinx-8056` | 2/5 | 0/3 | 3/3 | 0/3 | suspect |
| `sphinx-doc__sphinx-9367` | 5/5 | 3/3 | 3/3 | 3/3 | suspect |

| Agent | Mean resolved | Bugs resolved per run (of 8) | Runs | Std across runs | Mean cost per bug |
|---|---|---|---|---|---|
| A: Baseline: mini-swe-agent, unmodified | 57.5% | 4.60 | 5 | 11.2% | $0.009 |
| B: Our agent | 58.3% | 4.67 | 3 | 7.2% | $0.048 |
| C: Control: our selector over 3 baseline patches | 66.7% | 5.33 | 3 | 7.2% | $0.021 |
| D: Ablation: our agent's first attempt only | 54.2% | 4.33 | 3 | 7.2% | $0.000 |

Costs for C and D are only their **extra** cost: C also reuses 3 baseline runs per bug (its full cost is about 3 × A's plus the extra), and D reuses our agent's first attempt.

| Comparison | Difference | 95% interval | In bugs (of 8) |
|---|---|---|---|
| **Lift: our agent vs baseline** (B − A) | +0.8 pts | [-27.5, +30.0] | +0.07 |
| One attempt of ours vs one baseline run (D − A) | -3.3 pts | [-29.2, +20.8] | -0.27 |
| Gain from extra attempts + selection (B − D) | +4.2 pts | [-4.2, +20.8] | +0.33 |
| Our agent vs the control (B − C) | -8.3 pts | [-41.7, +20.8] | -0.67 |
| Our selector on baseline patches vs one baseline run (C − A) | +9.2 pts | [-10.8, +32.5] | +0.73 |

**No bug was judged clean** by the memorization checks (8 suspect), so a lift on clean bugs can't be computed. See `reports/contamination.md` for what drives the verdicts.

Total API spend recorded across all runs and checks: **$2.56**.
