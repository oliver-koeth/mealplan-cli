"""CLI integration tests for production calculation command wiring."""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.cli.main import app
from mealplan.domain.model import CANONICAL_MEAL_ORDER

runner = CliRunner()
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _normalized_stderr(stderr: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", stderr)


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


def test_calculate_command_passes_optional_vo2max(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            captured["request"] = request
            return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.cli.main.MealPlanCalculationService",
        FakeCalculationService,
    )

    result = runner.invoke(app, [*_required_calculate_args(), "--vo2max", "58"])

    assert result.exit_code == 0
    request = captured["request"]
    assert isinstance(request, MealPlanRequest)
    assert request.vo2max == 58


@pytest.mark.parametrize("vo2max", ["10", "100"])
def test_calculate_command_accepts_vo2max_range_boundaries(
    monkeypatch,
    vo2max: str,
) -> None:
    captured: dict[str, object] = {}

    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            captured["request"] = request
            return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.cli.main.MealPlanCalculationService",
        FakeCalculationService,
    )

    result = runner.invoke(app, [*_required_calculate_args(), "--vo2max", vo2max])

    assert result.exit_code == 0
    request = captured["request"]
    assert isinstance(request, MealPlanRequest)
    assert request.vo2max == int(vo2max)


def test_calculate_output_uses_service_response_payload(monkeypatch) -> None:
    expected = MealPlanResponse.model_validate(
        {
            "TDEE": 2222.5,
            "training_carbs_g": 12.0,
            "protein_g": 160.0,
            "carbs_g": 210.0,
            "fat_g": 77.0,
            "total_kcal": 2160.18,
            "meals": [
                {
                    "meal": meal,
                    "carbs_strategy": "low",
                    "carbs_g": 35.0,
                    "protein_g": 26.67,
                    "fat_g": 12.83,
                    "kcal": 360.03,
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


def test_calculate_command_emits_non_fatal_warnings_to_stderr(monkeypatch) -> None:
    warning = (
        "meal_assembly.protein_reduction: reduced breakfast protein from 40.00g to 33.33g "
        "to fit 133.33 kcal budget"
    )

    class FakeCalculationService:
        def __init__(self) -> None:
            self.warnings = (warning,)

        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.cli.main.MealPlanCalculationService",
        FakeCalculationService,
    )

    result = runner.invoke(app, _required_calculate_args())

    assert result.exit_code == 0
    assert json.loads(result.stdout) == MealPlanResponse.placeholder().model_dump(mode="json")
    assert result.stderr == f"Warning: {warning}\n"


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
            "--vo2max",
            "58",
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
        "total_kcal",
        "meals",
    }
    assert [meal["meal"] for meal in response["meals"]] == [
        "breakfast",
        "morning-snack",
        "training",
        "lunch",
        "afternoon-snack",
        "dinner",
        "evening-snack",
    ]


def test_calculate_default_format_is_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert "TDEE" in response
    assert "meals" in response


def test_calculate_text_format_outputs_top_level_and_canonical_meals() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
            "--format",
            "text",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    text_output = result.stdout
    assert "TDEE:" in text_output
    assert "training_carbs_g:" in text_output
    assert "protein_g:" in text_output
    assert "carbs_g:" in text_output
    assert "fat_g:" in text_output
    assert "total_kcal:" in text_output
    assert "carbs_strategy=" in text_output
    assert "kcal=" in text_output

    meal_lines = [
        line for line in text_output.splitlines() if line.startswith("- ")
    ]
    assert [line.split(":")[0][2:] for line in meal_lines] == list(CANONICAL_MEAL_ORDER)


def test_calculate_table_format_outputs_top_level_and_canonical_meals() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
            "--format",
            "table",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    table_output = result.stdout
    assert "| TDEE |" in table_output
    assert "| training_carbs_g |" in table_output
    assert "| protein_g |" in table_output
    assert "| carbs_g |" in table_output
    assert "| fat_g |" in table_output
    assert "| total_kcal |" in table_output
    assert "| meal | carbs_strategy | carbs_g | protein_g | fat_g | kcal |" in table_output

    meal_rows = [
        line
        for line in table_output.splitlines()
        if line.startswith("| ")
        and line.endswith(" |")
        and line.strip().split(" | ")[0].removeprefix("| ") in CANONICAL_MEAL_ORDER
    ]
    assert [
        row.strip().split(" | ")[0].removeprefix("| ") for row in meal_rows
    ] == list(CANONICAL_MEAL_ORDER)


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
    stderr = _normalized_stderr(result.stderr)
    assert "Missing option" in stderr
    assert "--age" in stderr


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
    stderr = _normalized_stderr(result.stderr)
    assert "Invalid value" in stderr
    assert "--gender" in stderr


@pytest.mark.parametrize(
    ("vo2max", "expected_fragment"),
    [
        ("9", "greater than or equal to 10"),
        ("101", "less than or equal to 100"),
    ],
)
def test_calculate_out_of_range_vo2max_returns_validation_exit_code(
    vo2max: str,
    expected_fragment: str,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
            "--vo2max",
            vo2max,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    stderr = _normalized_stderr(result.stderr)
    assert "vo2max" in stderr
    assert expected_fragment in stderr


def test_calculate_help_includes_optional_vo2max_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "calculate", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    stdout = _normalized_stderr(result.stdout)
    assert "--vo2max" in stdout
    assert "Optional VO2max" in stdout


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
    stderr = _normalized_stderr(result.stderr)
    assert "Invalid value" in stderr
    assert "--format" in stderr


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


def test_calculate_training_before_training_is_semantic_validation_error() -> None:
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
            "--training-before",
            "training",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error: training_session.training_before_meal: must not be 'training'" in result.stderr


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
