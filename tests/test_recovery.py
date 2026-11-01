from gated_agent.recovery import NUDGE, RESTART, ROLLBACK, StuckDetector


# ---------------------------------------------------------------- recovery and budget

def test_repeated_action_escalates_nudge_rollback_restart():
    d = StuckDetector()
    levels = []
    for _ in range(3):
        for _ in range(3):
            d.record("view", {"path": "a.py"}, "same", "", progress=False)
        assert d.reason()
        levels.append(d.escalate())
    assert levels == [NUDGE, ROLLBACK, RESTART]


def test_oscillating_edits_detected():
    d = StuckDetector()
    for i, diff in enumerate(["A", "B", "A"]):
        d.record("edit", {"n": i}, f"out{i}", diff, progress=True)
    assert "back and forth" in d.reason()


def test_progress_resets_idle_counter():
    d = StuckDetector(idle_steps=3)
    for i in range(2):
        d.record("view", {"i": i}, f"o{i}", "", progress=False)
    d.record("edit", {"i": 9}, "ok", "x", progress=True)
    assert d.reason() is None


def test_repeating_after_editing_a_file_is_not_a_loop():
    d = StuckDetector()
    for _ in range(3):
        d.record("edit", {"path": "/tmp/repro.py"}, "edited", "", progress=True, changed_files=True)
        d.record("register_repro", {"path": "/tmp/repro.py"}, "not registered", "", progress=True)
    assert d.reason() is None


def test_rollback_does_not_look_like_back_and_forth():
    d = StuckDetector()
    d.record("edit", {"n": 1}, "o1", "A", progress=True, changed_files=True)
    d.record("edit", {"n": 2}, "o2", "B", progress=True, changed_files=True)
    d.forget_code_history()  # rollback to A
    d.record("edit", {"n": 3}, "o3", "A", progress=True, changed_files=True)
    assert d.reason() is None


def test_no_idle_alarm_while_exploring():
    d = StuckDetector(idle_steps=3)
    for i in range(5):
        d.record("view", {"i": i}, f"o{i}", "", progress=False)
    assert d.reason(exploring=True) is None
    assert d.reason(exploring=False)


def test_short_repeated_outputs_are_not_a_loop():
    d = StuckDetector()
    for i in range(3):
        d.record("search", {"pattern": f"p{i}"}, "no matches", "", progress=False)
    assert d.reason() is None


def test_progress_resets_the_ladder_and_cap_limits_it():
    d = StuckDetector()
    assert d.escalate(cap=NUDGE) == NUDGE
    assert d.escalate(cap=NUDGE) == NUDGE  # exploring: never beyond a nudge
    assert d.escalate() == ROLLBACK
    d.progress_made()
    assert d.escalate() == NUDGE
