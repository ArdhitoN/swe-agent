from lift_eval.stats import bootstrap_diff, mean_rate, per_run_rates


def test_mean_rate_and_per_run_rates():
    outcomes = {"a": [True, False], "b": [True, True]}
    assert mean_rate(outcomes) == 0.75
    assert per_run_rates(outcomes) == [1.0, 0.5]


def test_bootstrap_diff_point_and_interval():
    a = {f"bug{i}": [False, False, False] for i in range(8)}
    b = {f"bug{i}": [i < 4] * 3 for i in range(8)}  # 4 of 8 bugs always fixed
    d, lo, hi = bootstrap_diff(a, b, n=2000)
    assert d == 0.5 and lo <= 0.5 <= hi and lo > 0
