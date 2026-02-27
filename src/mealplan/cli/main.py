"""CLI entrypoint for the mealplan command."""

from __future__ import annotations

import typer

from mealplan.application.contracts import ProbeRequest, SimulatedErrorKind
from mealplan.application.parsing import parse_contract
from mealplan.application.stub import run_probe
from mealplan.shared.exit_codes import map_exception_to_exit_code

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")

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
    request = parse_contract(ProbeRequest, {"simulate_error": simulate_error})
    response = run_probe(request)
    typer.echo(response.message)


def main() -> None:
    """Run the root Typer application."""
    try:
        app()
    except Exception as error:  # noqa: BLE001
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(int(map_exception_to_exit_code(error))) from None
