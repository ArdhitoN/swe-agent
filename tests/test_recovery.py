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
