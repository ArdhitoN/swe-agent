from gated_agent.select.selector import Evaluation, choose


# ---------------------------------------------------------------- selection

def ev(name, passes, regressions=(), lines=5, applies=True):
    return Evaluation(name=name, applies=applies, repro_passes=tuple(passes), regressions=list(regressions), patch_lines=lines)


def test_choose_prefers_more_reproductions_passed():
    idx, _ = choose([ev("a", [1, 0, 0]), ev("b", [1, 1, 0])])
    assert idx == 1


def test_choose_excludes_regressions_when_possible():
    idx, reason = choose([ev("a", [1, 1], regressions=["t1"]), ev("b", [1, 0])])
    assert idx == 1 and reason.startswith("verified")


def test_choose_majority_then_smallest():
    evals = [ev("a", [1, 1], lines=9), ev("b", [1, 1], lines=3), ev("c", [1, 1], lines=1)]
    assert choose(evals)[0] == 2
    # two identical-outcome candidates beat one different candidate with the same score
    evals = [ev("a", [1, 0], lines=1), ev("b", [0, 1], lines=5), ev("c", [0, 1], lines=6)]
    assert choose(evals)[0] == 1


def test_choose_falls_back_to_unverified():
    idx, reason = choose([ev("a", [1], regressions=["t"]), ev("b", [0], regressions=["t"])])
    assert idx == 0 and "UNVERIFIED" in reason


def test_choose_nothing_usable():
    assert choose([ev("a", [], lines=0), ev("b", [], applies=False)])[0] is None
