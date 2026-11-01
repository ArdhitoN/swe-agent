"""Save a pinned copy of the public per-bug results that the bug selection (`lift_eval/tasks.py`) uses.

Run once; the output in data/leaderboard_snapshot/ is committed so the draw can be reproduced
even if the public leaderboard changes later.
"""

import json
import urllib.request
from pathlib import Path

from lift_eval.config import REPO_ROOT

SNAPSHOT_DIR = REPO_ROOT / "data" / "leaderboard_snapshot"
LEADERBOARD_URL = "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json"
EXPERIMENTS_API = "https://api.github.com/repos/SWE-bench/experiments/commits/main"
PER_INSTANCE_URL = "https://raw.githubusercontent.com/SWE-bench/experiments/{sha}/evaluation/verified/{folder}/per_instance_details.json"
POOL_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows?dataset={dataset}&config=default&split={split}&offset=0&length=100"
)


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read())


def changed_files(patch: str) -> list[str]:
    """File paths touched by a unified diff (from its '+++ b/...' / '--- a/...' headers)."""
    files = set()
    for line in patch.splitlines():
        for prefix in ("+++ b/", "--- a/"):
            if line.startswith(prefix):
                files.add(line[len(prefix) :].strip())
    return sorted(files)


def fetch_snapshot(dataset: str, split: str, out_dir: Path = SNAPSHOT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _get_json(POOL_ROWS_URL.format(dataset=dataset, split=split))["rows"]
    pool = {r["row"]["instance_id"]: r["row"] for r in rows}
    # Only file *names* of each gold patch are kept: enough to check that dev and test bugs
    # don't touch the same files, without anyone reading the test fixes.
    gold_files = {iid: changed_files(row["patch"]) for iid, row in sorted(pool.items())}

    sha = _get_json(EXPERIMENTS_API)["sha"]
    leaderboard = _get_json(LEADERBOARD_URL)
    verified = next(lb for lb in leaderboard["leaderboards"] if lb["name"] == "Verified")
    runs = {}
    for entry in verified["results"]:
        if entry.get("agent") != "mini-SWE-agent":
            continue
        try:
            details = _get_json(PER_INSTANCE_URL.format(sha=sha, folder=entry["folder"]))
        except Exception as e:  # some folders have no per-instance file
            print(f"skip {entry['folder']}: {e}")
            continue
        runs[entry["folder"]] = {
            "name": entry["name"],
            "official_resolved_pct": entry["resolved"],
            "pool_resolved": {iid: bool(details.get(iid, {}).get("resolved")) for iid in sorted(pool)},
            "pool_reported": sorted(iid for iid in pool if iid in details),
        }
    meta = {
        "experiments_repo_commit": sha,
        "leaderboard_url": LEADERBOARD_URL,
        "pool_dataset": dataset,
        "pool_split": split,
        "n_pool": len(pool),
        "n_runs": len(runs),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out_dir / "runs.json").write_text(json.dumps(runs, indent=1, sort_keys=True) + "\n")
    (out_dir / "gold_files.json").write_text(json.dumps(gold_files, indent=1) + "\n")
    return meta
