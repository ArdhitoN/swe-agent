"""Command-line entry point behind the Makefile targets."""

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def show_config():
    """Print the locked experiment config."""
    from lift_eval.config import CONFIG_PATH

    print(CONFIG_PATH.read_text())



@app.command()
def fetch_snapshot():
    """Save the pinned public per-bug results used for bug selection (run once)."""
    from lift_eval.config import load_experiment
    from lift_eval.snapshot import fetch_snapshot as _fetch

    ds = load_experiment()["dataset"]
    print(_fetch(ds["pool"], ds["pool_split"]))


@app.command()
def select_tasks():
    """One-time seeded draw of the test and dev bugs (reruns give the same IDs)."""
    from lift_eval.config import load_experiment
    from lift_eval.tasks import select_tasks as _select

    result = _select(load_experiment())
    print(f"usable runs: {result['n_runs']} / {result['n_runs_total']}")
    print("test:", *result["test"], sep="\n  ")
    print("dev:", *result["dev"], sep="\n  ")



@app.command()
def check_images(pull: bool = typer.Option(False, help="Download missing images, check them, delete them again")):
    """Check each chosen bug's image: digest, future git history, internet access, emulation speed."""
    from lift_eval.images import check_images as _check
    from lift_eval.tasks import TASKS_DEV, TASKS_TEST

    ids = TASKS_TEST.read_text().split() + TASKS_DEV.read_text().split()
    for r in _check(ids, pull=pull):
        print(r)


if __name__ == "__main__":
    app()
