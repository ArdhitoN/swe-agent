from lift_eval.snapshot import changed_files
from lift_eval.tasks import draw, solve_rates, usable_runs

POOL = [f"django__django-{i}" for i in range(10)] + [f"sphinx-doc__sphinx-{i}" for i in range(10)]


def make_run(official_pct, solved, reported=POOL):
    return {
        "official_resolved_pct": official_pct,
        "pool_resolved": {iid: iid in solved for iid in POOL},
        "pool_reported": list(reported),
    }


def test_changed_files_reads_diff_headers():
    patch = "--- a/x/y.py\n+++ b/x/y.py\n@@ -1 +1 @@\n-a\n+b\n--- a/z.py\n+++ b/z.py\n"
    assert changed_files(patch) == ["x/y.py", "z.py"]


def test_usable_runs_drops_own_model_incomplete_and_broken_records():
    half = set(POOL[::2])
    runs = {
        "20250101_mini_gpt-5-mini": make_run(50, half),  # our own model: excluded
        "ok": make_run(50, half),
        "missing_bugs": make_run(50, half, reported=POOL[:-1]),  # doesn't report every bug
        "broken": make_run(70, set()),  # 0% on the pool vs 70% officially
    }
    assert list(usable_runs(runs, POOL, "gpt-5-mini")) == ["ok"]


def test_solve_rates():
    runs = {"a": make_run(50, {POOL[0]}), "b": make_run(50, {POOL[0], POOL[1]})}
    rates = solve_rates(runs, POOL)
    assert rates[POOL[0]] == 1.0 and rates[POOL[1]] == 0.5 and rates[POOL[2]] == 0.0


def _draw(seed, gold_files=None):
    rates = {iid: 0.5 for iid in POOL}
    rates[POOL[0]] = 0.0  # below the band: must never be drawn
    gold = gold_files or {iid: [f"{iid}.py"] for iid in POOL}
    return draw(
        rates,
        gold,
        seed=seed,
        band_low=0.1,
        band_high=0.9,
        test_per_repo={"django": 2, "sphinx-doc": 2},
        dev_per_repo={"django": 2, "sphinx-doc": 2},
    )


def test_draw_is_reproducible_and_respects_band_and_split():
    test1, dev1 = _draw(123)
    test2, dev2 = _draw(123)
    assert (test1, dev1) == (test2, dev2)
    assert POOL[0] not in test1 + dev1
    assert not set(test1) & set(dev1)
    assert sum(i.startswith("django") for i in test1) == 2


def test_dev_bugs_never_share_files_with_test_bugs():
    shared = {iid: ["django/shared.py"] if iid.startswith("django") else [f"{iid}.py"] for iid in POOL}
    shared["django__django-9"] = ["django/other.py"]
    shared["django__django-8"] = ["django/other2.py"]
    test, dev = _draw(7, shared)
    test_files = {f for i in test for f in shared[i]}
    assert all(not set(shared[i]) & test_files for i in dev)
