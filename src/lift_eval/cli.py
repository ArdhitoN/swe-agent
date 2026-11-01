"""Command-line entry point behind the Makefile targets."""

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def show_config():
    """Print the locked experiment config."""
    from lift_eval.config import CONFIG_PATH

    print(CONFIG_PATH.read_text())


if __name__ == "__main__":
    app()
