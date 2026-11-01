"""Load bug records (issue text, image, ...) from the official dataset the runs use."""

from functools import lru_cache


@lru_cache(maxsize=1)
def _rows(name: str, split: str) -> dict:
    from datasets import load_dataset

    return {row["instance_id"]: dict(row) for row in load_dataset(name, split=split)}


def get_instance(cfg: dict, instance_id: str) -> dict:
    return _rows(cfg["dataset"]["runs"], cfg["dataset"]["runs_split"])[instance_id]
