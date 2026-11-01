from gated_agent.budget import BugBudget


def test_budget_shares_and_rollover():
    b = BugBudget(250, 3.0)
    assert b.share(3) == (83, 1.0)
    b.spend(40, 0.2)  # first attempt used less than its share
    calls, cost = b.share(2)
    assert calls == 105 and abs(cost - 1.4) < 1e-9
