"""Check each bug's Docker image before any run.

For every image we record:
- its digest, so the exact image can be named later;
- whether the repo inside contains commits that come *after* the bug (a known SWE-bench
  loophole: `git log --all` can reveal the fix);
- whether the container can reach the internet (an agent could download the fixed code);
- how long a simple import takes under x86 emulation on this Mac.
"""

import json
import subprocess
import time

from lift_eval.config import REPO_ROOT
from lift_eval.dockerenv import docker_env, docker_executable, image_for

REPORT_JSON = REPO_ROOT / "reports" / "image_checks.json"

GIT_CHECK = r"""
cd /testbed
echo "head=$(git rev-parse HEAD)"
echo "head_date=$(git log -1 --format=%cI HEAD)"
echo "commits_reachable_from_head=$(git rev-list HEAD --count)"
echo "commits_not_in_head=$(git rev-list --all --not HEAD --count 2>/dev/null || echo 0)"
echo "refs=$(git for-each-ref --format='%(refname)' | tr '\n' ' ')"
echo "reflog_entries=$(git reflog 2>/dev/null | wc -l | tr -d ' ')"
echo "remotes=$(git remote | tr '\n' ' ')"
echo "stash_entries=$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
"""

NET_CHECK = (
    "python -c \"import urllib.request; urllib.request.urlopen('https://pypi.org/simple/pip/', timeout=8); print('net=yes')\""
    " 2>/dev/null || echo net=no"
)


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=docker_env())


def _parse(output: str) -> dict:
    out = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def check_image(instance_id: str) -> dict:
    docker = docker_executable()
    image = image_for(instance_id)
    result = {"instance_id": instance_id, "image": image}
    digest = _run([docker, "image", "inspect", "--format", "{{index .RepoDigests 0}}", image])
    if digest.returncode != 0:
        result["error"] = "image not pulled"
        return result
    result["digest"] = digest.stdout.strip()
    started = _run([docker, "run", "-d", "--rm", "--platform", "linux/amd64", image, "sleep", "900"])
    if started.returncode != 0:
        result["error"] = f"container failed to start: {started.stderr.strip()[:300]}"
        return result
    cid = started.stdout.strip()
    try:
        git = _run([docker, "exec", cid, "bash", "-c", GIT_CHECK])
        result.update(_parse(git.stdout))
        net = _run([docker, "exec", cid, "bash", "-lc", f"source /opt/miniconda3/bin/activate testbed; {NET_CHECK}"])
        result.update(_parse(net.stdout))
        module = "django" if instance_id.startswith("django") else "sphinx"
        t0 = time.time()
        imp = _run(
            [docker, "exec", cid, "bash", "-lc", f"source /opt/miniconda3/bin/activate testbed; python -c 'import {module}'"]
        )
        result["import_seconds"] = round(time.time() - t0, 1)
        result["import_ok"] = imp.returncode == 0
    finally:
        _run([docker, "rm", "-f", cid])
    return result


def has_image(instance_id: str) -> bool:
    return _run([docker_executable(), "image", "inspect", image_for(instance_id)]).returncode == 0


def ensure_image(instance_id: str) -> None:
    """Download a bug's image if it isn't on disk yet."""
    if not has_image(instance_id):
        _run([docker_executable(), "pull", "--platform", "linux/amd64", image_for(instance_id)], timeout=3600).check_returncode()


def remove_image(instance_id: str) -> None:
    """Delete a bug's image. Each image is ~4 GB, so we keep only the ones in use (see NOTES.md)."""
    _run([docker_executable(), "rmi", "-f", image_for(instance_id)])


def record_check(instance_id: str) -> dict:
    """Check one image and merge the result into reports/image_checks.json."""
    results = json.loads(REPORT_JSON.read_text()) if REPORT_JSON.exists() else {}
    results[instance_id] = check_image(instance_id)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return results[instance_id]


def check_images(instance_ids: list[str], pull: bool = False) -> list[dict]:
    """Check each image. With pull=True, missing images are downloaded, checked, then deleted again."""
    out = []
    for iid in instance_ids:
        pulled_here = False
        if not has_image(iid):
            if not pull:
                continue
            ensure_image(iid)
            pulled_here = True
        out.append(record_check(iid))
        if pulled_here:
            remove_image(iid)
    return out
