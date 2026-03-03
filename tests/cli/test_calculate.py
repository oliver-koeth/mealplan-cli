"""CLI integration tests for production calculation command wiring."""

from __future__ import annotations

import json
import subprocess
import sys

from typer.testing import CliRunner

from mealplan.application.contracts import MealPlanResponse
from mealplan.cli.main import app
from mealplan.domain.model import CANONICAL_MEAL_ORDER

runner = CliRunner()


def _required_calculate_args() -> list[str]:
    return [
        "calculate",
        "--age",
        "40",
        "--gender",
        "male",
        "--height",
        "180",
        "--weight",
        "75",
        "--activity",
        "medium",
        "--carbs",
        "low",
        "--training-tomorrow",
        "high",
    ]


def test_calculate_command_calls_application_service(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            captured["request"] = request
            return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.cli.main.MealPlanCalculationService",
        FakeCalculationService,
    )

    result = runner.invoke(app, _required_calculate_args())

    assert result.exit_code == 0
    assert "request" in captured


def test_calculate_output_uses_service_response_payload(monkeypatch) -> None:
    expected = MealPlanResponse.model_validate(
        {
            "TDEE": 2222.5,
            "training_carbs_g": 12.0,
            "protein_g": 160.0,
            "carbs_g": 210.0,
            "fat_g": 77.0,
            "meals": [
                {
                    "meal": meal,
                    "carbs_g": 35.0,
                    "protein_g": 26.67,
                    "fat_g": 12.83,
                }
                for meal in CANONICAL_MEAL_ORDER
            ],
        },
    )

    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            return expected

    monkeypatch.setattr(
        "mealplan.cli.main.MealPlanCalculationService",
        FakeCalculationService,
    )

    result = runner.invoke(app, _required_calculate_args())

    assert result.exit_code == 0
    assert json.loads(result.stdout) == expected.model_dump(mode="json")


def test_calculate_command_runs_with_canonical_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
            "--training-zones",
            '{"1": 20, "2": 40, "3": 0, "4": 0, "5": 0}',
            "--training-before",
            "lunch",
            "--format",
            "json",
            "--debug",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert set(response.keys()) == {
        "TDEE",
        "training_carbs_g",
        "protein_g",
        "carbs_g",
        "fat_g",
        "meals",
    }
    assert [meal["meal"] for meal in response["meals"]] == [
        "breakfast",
        "morning-snack",
        "lunch",
        "afternoon-snack",
        "dinner",
        "evening-snack",
    ]


def test_calculate_missing_required_option_returns_validation_exit_code() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Missing option '--age'" in result.stderr


def test_calculate_invalid_enum_option_returns_validation_exit_code() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "invalid",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Invalid value for '--gender'" in result.stderr


def test_calculate_invalid_format_choice_returns_validation_exit_code() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
            "--format",
            "xml",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Invalid value for '--format'" in result.stderr


def test_calculate_training_fields_are_parsed_then_validated_by_application() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
            "--training-zones",
            '{"2": 45}',
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert (
        "Error: training_session.training_before_meal: required when total zones_minutes > 0"
        in result.stderr
    )


def test_calculate_training_zones_accepts_json_string_input() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
            "--training-zones",
            '{"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}',
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert response["training_carbs_g"] == 0.0


def test_calculate_training_zones_invalid_json_returns_validation_exit_code() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calculate",
            "--age",
            "40",
            "--gender",
            "male",
            "--height",
            "180",
            "--weight",
            "75",
            "--activity",
            "medium",
            "--carbs",
            "low",
            "--training-tomorrow",
            "high",
            "--training-zones",
            "{",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error: training_zones: invalid JSON" in result.stderr
