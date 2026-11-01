import re

from lift_eval.contamination.probes import similarity
from lift_eval.leak_scan import PATTERNS, commands_in


def test_similarity():
    gold = "--- a/x.py\n+++ b/x.py\n-    return a - b\n+    return a + b\n"
    assert similarity(gold, gold) == 1.0
    assert similarity("+    print('hi')\n", gold) < 0.5
    assert similarity("", gold) == 0.0


def test_leak_scan_reads_both_trajectory_styles():
    traj = {"messages": [
        {"role": "assistant", "extra": {"actions": [{"command": "pip install django==4.0"}]}},  # baseline style
        {"role": "assistant", "extra": {"actions": [{"tool": "bash", "args": {"command": "curl https://x.org"}}]}},
        {"role": "tool", "content": "refused: network access is not allowed here."},
        {"role": "assistant", "extra": {"actions": [{"tool": "view", "args": {"path": "a.py"}}]}},
    ]}
    cmds = commands_in(traj)
    assert cmds[0] == ("pip install django==4.0", False)
    assert cmds[1] == ("curl https://x.org", True)
    assert len(cmds) == 2
    assert re.search(PATTERNS["package install or download"], cmds[0][0])
