"""CLI entrypoint for the mealplan command."""

import typer

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")


@app.callback()
def root() -> None:
    """Root CLI namespace for mealplan commands."""


def main() -> None:
    """Run the root Typer application."""
    app()
