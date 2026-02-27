"""CLI entrypoint for the mealplan command."""

import typer

from mealplan.application.stub import get_probe_message

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")


@app.callback()
def root() -> None:
    """Root CLI namespace for mealplan commands."""


@app.command("probe")
def probe_command() -> None:
    """Run a deterministic placeholder command."""
    typer.echo(get_probe_message())


def main() -> None:
    """Run the root Typer application."""
    app()
