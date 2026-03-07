"""CLI entrypoint for the mealplan command."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Literal

import typer

from mealplan.application.contracts import (
    MealPlanRequest,
    MealPlanResponse,
    ProbeRequest,
    SimulatedErrorKind,
)
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.application.stub import run_probe
from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, TrainingLoadTomorrow
from mealplan.shared.errors import ValidationError
from mealplan.shared.exit_codes import map_exception_to_exit_code

app = typer.Typer(no_args_is_help=True, help="Mealplan command-line interface.")
_DEBUG_MODE = False

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
    help="Output format: json|text|table.",
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
    training_before: str | None = TRAINING_BEFORE_OPTION,
    output_format: OutputFormat = OUTPUT_FORMAT_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Run production mealplan calculation from typed CLI inputs."""
    global _DEBUG_MODE
    _DEBUG_MODE = debug
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
    service = MealPlanCalculationService()
    response = service.calculate(request)
    for warning in getattr(service, "warnings", ()):
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo(_render_output(response=response, output_format=output_format))


def _build_training_session_payload(
    *,
    training_zones: str | None,
    training_before: str | None,
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


def _render_output(*, response: MealPlanResponse, output_format: OutputFormat) -> str:
    mealplan_response = response
    if output_format == "json":
        return mealplan_response.model_dump_json()
    if output_format == "text":
        return _render_text_output(mealplan_response)
    return _render_table_output(mealplan_response)


def _render_text_output(response: MealPlanResponse) -> str:
    payload = response.model_dump(mode="json")
    lines = [
        f"TDEE: {payload['TDEE']}",
        f"training_carbs_g: {payload['training_carbs_g']}",
        f"protein_g: {payload['protein_g']}",
        f"carbs_g: {payload['carbs_g']}",
        f"fat_g: {payload['fat_g']}",
        f"total_kcal: {payload['total_kcal']}",
        "meals:",
    ]
    for meal in payload["meals"]:
        meal_name = meal["meal"]
        lines.append(
            f"- {meal_name}: carbs_strategy={meal['carbs_strategy']} carbs_g={meal['carbs_g']} "
            f"protein_g={meal['protein_g']} fat_g={meal['fat_g']} kcal={meal['kcal']}"
        )
    return "\n".join(lines)


def _render_table_output(response: MealPlanResponse) -> str:
    payload = response.model_dump(mode="json")
    lines = [
        "| field | value |",
        "| --- | --- |",
        f"| TDEE | {payload['TDEE']} |",
        f"| training_carbs_g | {payload['training_carbs_g']} |",
        f"| protein_g | {payload['protein_g']} |",
        f"| carbs_g | {payload['carbs_g']} |",
        f"| fat_g | {payload['fat_g']} |",
        f"| total_kcal | {payload['total_kcal']} |",
        "",
        "| meal | carbs_strategy | carbs_g | protein_g | fat_g | kcal |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for meal in payload["meals"]:
        meal_name = meal["meal"]
        lines.append(
            f"| {meal_name} | {meal['carbs_strategy']} | {meal['carbs_g']} | {meal['protein_g']} | "
            f"{meal['fat_g']} | {meal['kcal']} |"
        )
    return "\n".join(lines)


def main() -> None:
    """Run the root Typer application."""
    try:
        app()
    except Exception as error:  # noqa: BLE001
        typer.echo(f"Error: {error}", err=True)
        if _DEBUG_MODE:
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        raise SystemExit(int(map_exception_to_exit_code(error))) from None
