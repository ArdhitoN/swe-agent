# Bug selection

Rule: score each bug by the share of public mini-swe-agent runs that fixed it; keep bugs inside the band; draw test bugs per repo with the seed; draw dev bugs from the rest of the band, skipping any that touch the same files as a test bug's fix. Full rule: `src/lift_eval/tasks.py`.

Seed `20261101`, band 10%–86%.
Difficulty is the share of **36** usable public mini-swe-agent runs (of 40 in the snapshot) that fixed each bug. Runs matching `gpt-5-mini` (our own model) are excluded.

- Below the band: 11 bugs
- In the band: 22 bugs
- Above the band: 17 bugs

| Bug | Fixed by (share of runs) | Role |
|---|---|---|
| `sphinx-doc__sphinx-11510` | 0% |  |
| `sphinx-doc__sphinx-7590` | 0% |  |
| `sphinx-doc__sphinx-7748` | 0% |  |
| `sphinx-doc__sphinx-9229` | 0% |  |
| `sphinx-doc__sphinx-9461` | 3% |  |
| `django__django-12273` | 6% |  |
| `django__django-12406` | 6% |  |
| `sphinx-doc__sphinx-7985` | 6% |  |
| `django__django-12308` | 8% |  |
| `django__django-12325` | 8% |  |
| `sphinx-doc__sphinx-8548` | 8% |  |
| `sphinx-doc__sphinx-10435` | 11% | dev |
| `django__django-11790` | 17% | **test** |
| `django__django-11885` | 19% | dev |
| `sphinx-doc__sphinx-8056` | 19% | **test** |
| `django__django-11964` | 22% | dev |
| `sphinx-doc__sphinx-8638` | 25% | dev |
| `sphinx-doc__sphinx-8265` | 33% |  |
| `django__django-12193` | 42% | **test** |
| `django__django-11848` | 53% |  |
| `sphinx-doc__sphinx-10673` | 61% |  |
| `django__django-12774` | 64% | **test** |
| `sphinx-doc__sphinx-10323` | 64% | **test** |
| `sphinx-doc__sphinx-8551` | 67% |  |
| `sphinx-doc__sphinx-9281` | 67% |  |
| `django__django-12039` | 72% |  |
| `django__django-11815` | 75% | **test** |
| `django__django-12304` | 75% | dev |
| `sphinx-doc__sphinx-9230` | 78% | dev |
| `django__django-12276` | 81% |  |
| `django__django-12708` | 81% |  |
| `sphinx-doc__sphinx-7757` | 83% | **test** |
| `sphinx-doc__sphinx-9367` | 83% | **test** |
| `django__django-11951` | 86% |  |
| `django__django-12143` | 86% |  |
| `django__django-12262` | 86% |  |
| `sphinx-doc__sphinx-8035` | 86% |  |
| `sphinx-doc__sphinx-8269` | 86% |  |
| `sphinx-doc__sphinx-8721` | 86% |  |
| `sphinx-doc__sphinx-9320` | 86% |  |
| `sphinx-doc__sphinx-9698` | 86% |  |
| `django__django-12209` | 89% |  |
| `django__django-12713` | 89% |  |
| `sphinx-doc__sphinx-8475` | 89% |  |
| `django__django-11880` | 92% |  |
| `django__django-12050` | 92% |  |
| `django__django-9296` | 92% |  |
| `django__django-11999` | 94% |  |
| `django__django-12155` | 94% |  |
| `sphinx-doc__sphinx-10466` | 94% |  |
