"""CLI entrypoint for the mealplan command."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Literal

import typer

from mealplan.application.contracts import (
    FoodLogSearchRequest,
    FoodLogUpsertRequest,
    MealPlanRequest,
    MealPlanResponse,
    ProbeRequest,
    SimulatedErrorKind,
)
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.application.stub import run_probe
from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, TrainingLoadTomorrow
from mealplan.infrastructure import (
    JsonCalendarStore,
    JsonFoodLogStore,
    JsonUsersStore,
    canonicalize_user_email,
    resolve_user_partitioned_path,
    resolve_users_store_path,
)
from mealplan.shared.errors import ValidationError
from mealplan.shared.exit_codes import map_exception_to_exit_code
from mealplan.web import run_ui_server

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Mealplan command-line interface.",
)
log_app = typer.Typer(
    no_args_is_help=False,
    invoke_without_command=True,
    help=(
        "Create or update food-log entries.\n\n"
        "JSON example:\n"
        "mealplan log --json "
        "'{\"date\":\"20260408\",\"meal\":\"lunch\",\"name\":\"Oats\",\"kcal\":380,"
        "\"carbs\":55,\"fat\":8,\"protein\":14,\"fiber\":9}'"
    ),
)
app.add_typer(log_app, name="log")
_DEBUG_MODE = False

SIMULATED_ERROR_OPTION = typer.Option(
    default=None,
    help="Simulate a named error pathway for scaffolding tests.",
)
AGE_OPTION = typer.Option(..., "--age", help="Age in years.")
GENDER_OPTION = typer.Option(..., "--gender", help="Gender: male|female.")
HEIGHT_OPTION = typer.Option(..., "--height", help="Height in centimeters.")
WEIGHT_OPTION = typer.Option(..., "--weight", help="Weight in kilograms.")
VO2MAX_OPTION = typer.Option(
    None,
    "--vo2max",
    help="Optional VO2max in ml/kg/min.",
)
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
DATE_OPTION = typer.Option(
    ...,
    "--date",
    help="Date key in YYYYMMDD format used for calendar persistence.",
)
DEBUG_OPTION = typer.Option(
    False,
    "--debug",
    help="Enable debug output placeholder.",
)
UI_OPTION = typer.Option(
    False,
    "--ui",
    help="Start local web UI server mode.",
)
OutputFormat = Literal["json", "text", "table"]
CALENDAR_STORE_PATH_ENV = "MEALPLAN_CALENDAR_STORE_PATH"
FOOD_LOG_STORE_PATH_ENV = "MEALPLAN_FOOD_LOG_STORE_PATH"
LOG_UUID_OPTION = typer.Option(
    None,
    "--uuid",
    help="Existing UUID for update operations.",
)
LOG_DATE_OPTION = typer.Option(
    None,
    "--date",
    help="Date key in YYYYMMDD format.",
)
LOG_MEAL_OPTION = typer.Option(
    None,
    "--meal",
    help="Meal name.",
)
LOG_NAME_OPTION = typer.Option(
    None,
    "--name",
    help="Food name.",
)
LOG_KCAL_OPTION = typer.Option(
    None,
    "--kcal",
    help="Calories in kcal.",
)
LOG_CARBS_OPTION = typer.Option(
    None,
    "--carbs",
    help="Carbs in grams.",
)
LOG_FAT_OPTION = typer.Option(
    None,
    "--fat",
    help="Fat in grams.",
)
LOG_PROTEIN_OPTION = typer.Option(
    None,
    "--protein",
    help="Protein in grams.",
)
LOG_FIBER_OPTION = typer.Option(
    None,
    "--fiber",
    help="Fiber in grams.",
)
LOG_QUANTITY_OPTION = typer.Option(
    None,
    "--quantity",
    help="Optional quantity multiplier. Defaults to 1.0.",
)
LOG_JSON_OPTION = typer.Option(
    None,
    "--json",
    help="One-shot JSON payload for create/update. Include uuid to update.",
)
USER_OPTION = typer.Option(
    None,
    "--user",
    help="Optional user email for per-user calendar/log storage.",
)


@app.callback()
def root(ctx: typer.Context, ui: bool = UI_OPTION) -> None:
    """Root CLI namespace for mealplan commands."""
    if ui:
        if ctx.invoked_subcommand is not None:
            raise ValidationError("--ui cannot be combined with subcommands")
        run_ui_server()
        raise typer.Exit(code=0)


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
    vo2max: int | None = VO2MAX_OPTION,
    activity: ActivityLevel = ACTIVITY_OPTION,
    carbs: CarbMode = CARBS_OPTION,
    training_tomorrow: TrainingLoadTomorrow = TRAINING_TOMORROW_OPTION,
    training_zones: str | None = TRAINING_ZONES_OPTION,
    training_before: str | None = TRAINING_BEFORE_OPTION,
    output_format: OutputFormat = OUTPUT_FORMAT_OPTION,
    date: str = DATE_OPTION,
    user: str | None = USER_OPTION,
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
        "vo2max": vo2max,
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
    user_email = _resolve_user_email(user=user)
    _persist_calendar_entry(date_key=date, response=response, user_email=user_email)
    for warning in getattr(service, "warnings", ()):
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo(_render_output(response=response, output_format=output_format))


@app.command("calendar")
def calendar_command(
    date: str = DATE_OPTION,
    output_format: OutputFormat = OUTPUT_FORMAT_OPTION,
    user: str | None = USER_OPTION,
) -> None:
    """Retrieve a persisted meal plan by date."""
    user_email = _resolve_user_email(user=user)
    store = JsonCalendarStore(_calendar_store_path(user_email=user_email))
    persisted_payload = store.get(date_key=date)
    response = parse_contract(MealPlanResponse, persisted_payload)
    typer.echo(_render_output(response=response, output_format=output_format))


@log_app.callback()
def log_command(
    ctx: typer.Context,
    uuid: str | None = LOG_UUID_OPTION,
    date: str | None = LOG_DATE_OPTION,
    meal: str | None = LOG_MEAL_OPTION,
    name: str | None = LOG_NAME_OPTION,
    kcal: float | None = LOG_KCAL_OPTION,
    carbs: float | None = LOG_CARBS_OPTION,
    fat: float | None = LOG_FAT_OPTION,
    protein: float | None = LOG_PROTEIN_OPTION,
    fiber: float | None = LOG_FIBER_OPTION,
    quantity: float | None = LOG_QUANTITY_OPTION,
    json_payload: str | None = LOG_JSON_OPTION,
    user: str | None = USER_OPTION,
) -> None:
    """Create or update food-log entries."""
    if ctx.invoked_subcommand is not None:
        return
    payload = _build_log_payload(
        uuid=uuid,
        date=date,
        meal=meal,
        name=name,
        kcal=kcal,
        carbs=carbs,
        fat=fat,
        protein=protein,
        fiber=fiber,
        quantity=quantity,
        json_payload=json_payload,
    )
    request = parse_contract(FoodLogUpsertRequest, payload)
    user_email = _resolve_user_email(user=user)
    store = JsonFoodLogStore(_food_log_store_path(user_email=user_email))
    if request.uuid is not None:
        response = store.update(request=request)
    else:
        response = store.create(request=request)
    typer.echo(response.model_dump_json())


@log_app.command("search")
def log_search_command(
    date: str | None = LOG_DATE_OPTION,
    name: str | None = LOG_NAME_OPTION,
    meal: str | None = LOG_MEAL_OPTION,
    user: str | None = USER_OPTION,
) -> None:
    """Search food-log entries with optional filters."""
    request = parse_contract(
        FoodLogSearchRequest,
        {"date": date, "name": name, "meal": meal},
    )
    user_email = _resolve_user_email(user=user)
    store = JsonFoodLogStore(_food_log_store_path(user_email=user_email))
    response = store.search(request=request)
    typer.echo(json.dumps([entry.model_dump(mode="json") for entry in response]))


def _persist_calendar_entry(
    *,
    date_key: str,
    response: MealPlanResponse,
    user_email: str | None = None,
) -> None:
    store = JsonCalendarStore(_calendar_store_path(user_email=user_email))
    store.save(date_key=date_key, payload=response.model_dump(mode="json"))


def _calendar_store_path(*, user_email: str | None = None) -> Path:
    configured_path = os.getenv(CALENDAR_STORE_PATH_ENV)
    if configured_path:
        calendar_path = Path(configured_path).expanduser()
    else:
        calendar_path = Path.home() / ".mealplan" / "calendar.json"
    if user_email is None:
        return calendar_path
    return resolve_user_partitioned_path(
        storage_directory=calendar_path.parent,
        email=user_email,
        suffix_filename=calendar_path.name,
    )


def _food_log_store_path(*, user_email: str | None = None) -> Path:
    configured_path = os.getenv(FOOD_LOG_STORE_PATH_ENV)
    if configured_path:
        food_log_path = Path(configured_path).expanduser()
    else:
        food_log_path = Path.home() / ".mealplan" / "food-log.json"
    if user_email is None:
        return food_log_path
    return resolve_user_partitioned_path(
        storage_directory=food_log_path.parent,
        email=user_email,
        suffix_filename=food_log_path.name,
    )


def _resolve_user_email(*, user: str | None) -> str | None:
    if user is None:
        return None
    canonical_email = canonicalize_user_email(user)
    users_store = JsonUsersStore(resolve_users_store_path())
    persisted_user = users_store.get_by_email(email=canonical_email)
    if persisted_user is None:
        raise ValidationError(f"user: unknown user {canonical_email!r}")
    return persisted_user.email


def _build_log_payload(
    *,
    uuid: str | None,
    date: str | None,
    meal: str | None,
    name: str | None,
    kcal: float | None,
    carbs: float | None,
    fat: float | None,
    protein: float | None,
    fiber: float | None,
    quantity: float | None,
    json_payload: str | None,
) -> dict[str, object]:
    flagged_values = [uuid, date, meal, name, kcal, carbs, fat, protein, fiber, quantity]
    if json_payload is not None:
        if any(value is not None for value in flagged_values):
            raise ValidationError("--json cannot be combined with individual field flags")
        return _parse_log_json_payload(json_payload)

    missing_required = [
        option
        for option, value in (
            ("--date", date),
            ("--meal", meal),
            ("--name", name),
            ("--kcal", kcal),
            ("--carbs", carbs),
            ("--fat", fat),
            ("--protein", protein),
            ("--fiber", fiber),
        )
        if value is None
    ]
    if missing_required:
        raise ValidationError(f"log: missing required flags: {', '.join(missing_required)}")

    payload: dict[str, object] = {
        "date": date,
        "meal": meal,
        "name": name,
        "kcal": kcal,
        "carbs": carbs,
        "fat": fat,
        "protein": protein,
        "fiber": fiber,
    }
    if uuid is not None:
        payload["uuid"] = uuid
    if quantity is not None:
        payload["quantity"] = quantity
    return payload


def _parse_log_json_payload(raw_payload: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError as error:
        raise ValidationError(f"json: invalid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValidationError("json: expected JSON object payload")
    return dict(parsed)


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
        f"training_kcal: {payload['training_kcal']}",
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
        f"| training_kcal | {payload['training_kcal']} |",
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
