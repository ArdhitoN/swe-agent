"""One budget per bug, shared by all attempts: the baseline's own limits (250 calls, $3).

Each attempt gets a fair share of what's left; whatever an attempt doesn't use rolls over.
"""


class BugBudget:
    def __init__(self, max_calls: int, max_cost: float):
        self.max_calls = max_calls
        self.max_cost = max_cost
        self.calls = 0
        self.cost = 0.0

    @property
    def calls_left(self) -> int:
        return max(0, self.max_calls - self.calls)

    @property
    def cost_left(self) -> float:
        return max(0.0, self.max_cost - self.cost)

    def share(self, attempts_left: int) -> tuple[int, float]:
        attempts_left = max(1, attempts_left)
        return self.calls_left // attempts_left, self.cost_left / attempts_left

    def spend(self, calls: int, cost: float) -> None:
        self.calls += calls
        self.cost += cost

    def exhausted(self, min_calls: int = 10) -> bool:
        return self.calls_left < min_calls or self.cost_left <= 0.0
