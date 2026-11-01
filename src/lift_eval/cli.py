"""Command-line entry point behind the Makefile targets."""

import json

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



def _bug_list(bugs: str) -> list[str]:
    from lift_eval.tasks import TASKS_DEV, TASKS_TEST

    if bugs == "test":
        return TASKS_TEST.read_text().split()
    if bugs == "dev":
        return TASKS_DEV.read_text().split()
    return bugs.split(",")


@app.command()
def run_baseline(
    bugs: str = typer.Option("test", help="'test', 'dev', or comma-separated bug IDs"),
    runs: int = typer.Option(0, help="Number of runs (0 = the number in the config)"),
    first_run: int = typer.Option(1, help="Number of the first run, e.g. 2 to add runs 2..N"),
    keep_images: bool = typer.Option(False, help="Don't delete images afterwards"),
    expected_cost: float = typer.Option(0.5, help="Refuse to start a run if spent + this would pass the cap"),
):
    """Baseline (Arm A): unmodified mini-swe-agent, graded with the official harness, one bug at a time."""
    from lift_eval.config import load_experiment
    from lift_eval.runners.run_baseline import run_baseline as _run, run_dir
    from lift_eval.runners.schedule import run_schedule

    cfg = load_experiment()
    n = runs or cfg["runs"]["A"]
    names = [f"run_{k}" for k in range(first_run, first_run + n)]
    run_schedule(
        cfg, _bug_list(bugs), names, _run, lambda r, i: run_dir("A", r, i), expected_cost, keep_images
    )



@app.command()
def leak_scan():
    """Scan every trajectory of every agent for commands that could reveal the fix."""
    from lift_eval.leak_scan import scan, write_report

    print(write_report(scan()))


@app.command()
def contamination(probe: bool = typer.Option(True, help="Run the paid probes P1/P2 (skipped if already saved)")):
    """Memorization checks on the test bugs."""
    from lift_eval.config import load_experiment
    from lift_eval.contamination import probes
    from lift_eval.tasks import TASKS_TEST

    cfg = load_experiment()
    bugs = TASKS_TEST.read_text().split()
    saved = probes.PROBES_DIR / "probes.json"
    data = probes.run_probes(cfg, bugs) if probe else (json.loads(saved.read_text()) if saved.exists() else {})
    print(probes.write_report(probes.classify(cfg, data, bugs), cfg))


@app.command()
def grade_all(arm: str = typer.Option("", help="Only this agent's runs (A, B, C or D); default all")):
    """Grade every run that has a patch but no grade yet (the schedules normally grade as they go)."""
    from lift_eval import images
    from lift_eval.config import load_experiment
    from lift_eval.grade import grade_run
    from lift_eval.spend import RESULTS_DIR

    cfg = load_experiment()
    for preds in sorted(RESULTS_DIR.glob(f"{arm or '*'}/run_*/*/preds.json")):
        run = preds.parent
        if not (run / "resolved.json").exists():
            images.ensure_image(run.name)
            print(run, grade_run(run, cfg["dataset"]["runs"], cfg["dataset"]["runs_split"]))


@app.command()
def report():
    """Build reports/summary.md from saved results only (no API key needed)."""
    from lift_eval.contamination.probes import REPORT as CONTAM
    from lift_eval.tasks import TASKS_TEST

    verdicts_path = CONTAM.with_suffix(".json")
    verdicts = json.loads(verdicts_path.read_text()) if verdicts_path.exists() else None
    from lift_eval.report import build_report

    print(build_report(TASKS_TEST.read_text().split(), verdicts))


if __name__ == "__main__":
    app()
