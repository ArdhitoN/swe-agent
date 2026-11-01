"""Where Docker lives on this machine, shared by every runner so all agents use the same setup."""

import os
import shutil
from pathlib import Path

# Docker Desktop ships its own, current CLI here. An older CLI elsewhere on PATH can't talk to a new daemon.
DESKTOP_CLI = Path.home() / ".docker" / "bin" / "docker"
DESKTOP_SOCKET = Path.home() / ".docker" / "run" / "docker.sock"


def docker_executable() -> str:
    return str(DESKTOP_CLI) if DESKTOP_CLI.exists() else (shutil.which("docker") or "docker")


def docker_env() -> dict[str, str]:
    """Environment for subprocesses: the right docker CLI first on PATH, and the Docker Desktop socket."""
    env = dict(os.environ)
    env["PATH"] = f"{DESKTOP_CLI.parent}{os.pathsep}{env.get('PATH', '')}"
    env["MSWEA_DOCKER_EXECUTABLE"] = docker_executable()  # read by mini-swe-agent's Docker environment
    if DESKTOP_SOCKET.exists() and "DOCKER_HOST" not in env:
        env["DOCKER_HOST"] = f"unix://{DESKTOP_SOCKET}"  # read by the grader's Docker SDK
    return env


def image_for(instance_id: str) -> str:
    """The public SWE-bench image for a bug (same naming as mini-swe-agent and the dataset)."""
    return f"docker.io/swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest".lower()
