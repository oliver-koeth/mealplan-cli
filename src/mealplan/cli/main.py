"""CLI entrypoint for the mealplan command."""

from __future__ import annotations

from typing import Literal, TypeAlias

import typer

from mealplan.application.stub import get_probe_message
from mealplan.shared.exit_codes import map_exception_to_exit_code

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")

SimulatedErrorKind: TypeAlias = Literal[
    "validation",
    "domain",
    "config",
    "output",
    "runtime",
]
SIMULATED_ERROR_OPTION = typer.Option(
    default=None,
    help="Simulate a named error pathway for scaffolding tests.",
)


@app.callback()
def root() -> None:
    """Root CLI namespace for mealplan commands."""


@app.command("probe")
def probe_command(
    simulate_error: SimulatedErrorKind | None = SIMULATED_ERROR_OPTION,
) -> None:
    """Run a deterministic placeholder command."""
    typer.echo(get_probe_message(simulate_error=simulate_error))


def main() -> None:
    """Run the root Typer application."""
    try:
        app()
    except Exception as error:  # noqa: BLE001
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(int(map_exception_to_exit_code(error))) from None
