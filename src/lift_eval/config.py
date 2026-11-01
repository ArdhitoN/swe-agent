"""Load the experiment config and the API key file."""

import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "experiment.yaml"
# The key lives outside the repo so it can never be committed. Override with SWE_AGENT_ENV_FILE.
DEFAULT_ENV_FILE = Path.home() / ".config" / "test-gated-swe-agent" / ".env"


def load_experiment(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines into os.environ, without overwriting variables that are already set."""
    path = Path(os.getenv("SWE_AGENT_ENV_FILE", path or DEFAULT_ENV_FILE))
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
