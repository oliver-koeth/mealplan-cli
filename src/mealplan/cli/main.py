"""CLI entrypoint for the mealplan command."""

from __future__ import annotations

import json
from typing import Literal

import typer

from mealplan.application.contracts import MealPlanRequest, ProbeRequest, SimulatedErrorKind
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.application.stub import run_probe
from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, MealName, TrainingLoadTomorrow
from mealplan.shared.errors import ValidationError
from mealplan.shared.exit_codes import map_exception_to_exit_code

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")

SIMULATED_ERROR_OPTION = typer.Option(
    default=None,
    help="Simulate a named error pathway for scaffolding tests.",
)
AGE_OPTION = typer.Option(..., "--age", help="Age in years.")
GENDER_OPTION = typer.Option(..., "--gender", help="Gender: male|female.")
HEIGHT_OPTION = typer.Option(..., "--height", help="Height in centimeters.")
WEIGHT_OPTION = typer.Option(..., "--weight", help="Weight in kilograms.")
ACTIVITY_OPTION = typer.Option(..., "--activity", help="Activity level.")
CARBS_OPTION = typer.Option(..., "--carbs", help="Carb mode.")
TRAINING_TOMORROW_OPTION = typer.Option(
    ...,
    "--training-tomorrow",
    help="Training load expected tomorrow.",
)
TRAINING_ZONES_OPTION = typer.Option(
    None,
    "--training-zones",
    help="Training zones JSON string (e.g. '{\"2\": 45}').",
)
TRAINING_BEFORE_OPTION = typer.Option(
    None,
    "--training-before",
    help="Meal before training.",
)
OUTPUT_FORMAT_OPTION = typer.Option(
    "json",
    "--format",
    help="Output format placeholder.",
)
DEBUG_OPTION = typer.Option(
    False,
    "--debug",
    help="Enable debug output placeholder.",
)
OutputFormat = Literal["json", "text", "table"]


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


@app.command("calculate")
def calculate_command(
    age: int = AGE_OPTION,
    gender: Gender = GENDER_OPTION,
    height: int = HEIGHT_OPTION,
    weight: float = WEIGHT_OPTION,
    activity: ActivityLevel = ACTIVITY_OPTION,
    carbs: CarbMode = CARBS_OPTION,
    training_tomorrow: TrainingLoadTomorrow = TRAINING_TOMORROW_OPTION,
    training_zones: str | None = TRAINING_ZONES_OPTION,
    training_before: MealName | None = TRAINING_BEFORE_OPTION,
    output_format: OutputFormat = OUTPUT_FORMAT_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Run production mealplan calculation from typed CLI inputs."""
    request_payload: dict[str, object] = {
        "age": age,
        "gender": gender,
        "height_cm": height,
        "weight_kg": weight,
        "activity_level": activity,
        "carb_mode": carbs,
        "training_load_tomorrow": training_tomorrow,
    }
    training_session = _build_training_session_payload(
        training_zones=training_zones,
        training_before=training_before,
    )
    if training_session is not None:
        request_payload["training_session"] = training_session

    request = parse_contract(MealPlanRequest, request_payload)
    response = MealPlanCalculationService().calculate(request)
    _ = (output_format, debug)
    typer.echo(response.model_dump_json())


def _build_training_session_payload(
    *,
    training_zones: str | None,
    training_before: MealName | None,
) -> dict[str, object] | None:
    if training_zones is None and training_before is None:
        return None

    zones_minutes: object = {}
    if training_zones is not None:
        try:
            zones_minutes = json.loads(training_zones)
        except json.JSONDecodeError as error:
            raise ValidationError(f"training_zones: invalid JSON: {error.msg}") from error

    if not isinstance(zones_minutes, dict):
        raise ValidationError("training_zones: expected JSON object mapping zone keys to minutes")

    payload: dict[str, object] = {"zones_minutes": zones_minutes}
    if training_before is not None:
        payload["training_before_meal"] = training_before
    return payload


def main() -> None:
    """Run the root Typer application."""
    try:
        app()
    except Exception as error:  # noqa: BLE001
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(int(map_exception_to_exit_code(error))) from None
