# Memorization checks

Could the model have memorized these bugs' fixes? Thresholds were fixed before looking at results:
P2 memorized at similarity ≥ 0.8, P3 near-identical at ≥ 0.9, P4 too early within 3 steps.

| Bug | Verdict | P1 file from issue alone | P2 fix from ID alone (similarity) | P3 near-identical to official fix | P4 edit too early |
|---|---|---|---|---|---|
| `django__django-11790` | **suspect** | yes | 0.0 | no | 40% of runs |
| `django__django-11815` | **suspect** | yes | 0.0 | no | 0% of runs |
| `django__django-12193` | **suspect** | yes | 0.0 | no | 33% of runs |
| `django__django-12774` | **suspect** | yes | 0.0 | no | 20% of runs |
| `sphinx-doc__sphinx-10323` | **suspect** | yes | 0.0 | no | 33% of runs |
| `sphinx-doc__sphinx-7757` | **suspect** | yes | 0.0 | no | 0% of runs |
| `sphinx-doc__sphinx-8056` | **suspect** | yes | 0.0 | no | 0% of runs |
| `sphinx-doc__sphinx-9367` | **suspect** | yes | 0.0 | no | 50% of runs |
