"""CLI tests for controlled error-to-exit-code handling."""

from __future__ import annotations

import subprocess
import sys

import pytest

from mealplan.shared.errors import DomainRuleError, ValidationError


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


def test_probe_validation_error_returns_validation_exit_code() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "probe", "--simulate-error", "validation"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error: simulated validation failure" in result.stderr


def test_probe_domain_error_returns_domain_exit_code() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "probe", "--simulate-error", "domain"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert "Error: simulated domain rule failure" in result.stderr


def test_probe_runtime_error_returns_runtime_exit_code() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "probe", "--simulate-error", "runtime"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 4
    assert "Error: simulated runtime failure" in result.stderr


def test_calculate_validation_error_maps_to_validation_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mealplan.cli.main import main

    class FakeCalculationService:
        def calculate(self, request: object) -> object:
            _ = request
            raise ValidationError("simulated validation failure")

    monkeypatch.setattr("mealplan.cli.main.MealPlanCalculationService", FakeCalculationService)
    monkeypatch.setattr(sys, "argv", ["mealplan", *_required_calculate_args()])

    with pytest.raises(SystemExit) as error_info:
        main()

    assert error_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Error: simulated validation failure" in stderr


def test_calculate_domain_error_maps_to_domain_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mealplan.cli.main import main

    class FakeCalculationService:
        def calculate(self, request: object) -> object:
            _ = request
            raise DomainRuleError("simulated domain rule failure")

    monkeypatch.setattr("mealplan.cli.main.MealPlanCalculationService", FakeCalculationService)
    monkeypatch.setattr(sys, "argv", ["mealplan", *_required_calculate_args()])

    with pytest.raises(SystemExit) as error_info:
        main()

    assert error_info.value.code == 3
    stderr = capsys.readouterr().err
    assert "Error: simulated domain rule failure" in stderr


def test_calculate_runtime_error_maps_to_runtime_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mealplan.cli.main import main

    class FakeCalculationService:
        def calculate(self, request: object) -> object:
            _ = request
            raise RuntimeError("simulated runtime failure")

    monkeypatch.setattr("mealplan.cli.main.MealPlanCalculationService", FakeCalculationService)
    monkeypatch.setattr(sys, "argv", ["mealplan", *_required_calculate_args()])

    with pytest.raises(SystemExit) as error_info:
        main()

    assert error_info.value.code == 4
    stderr = capsys.readouterr().err
    assert "Error: simulated runtime failure" in stderr


def test_calculate_error_output_is_concise_by_default() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
            "--training-zones",
            '{"1":',
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error: training_zones: invalid JSON" in result.stderr
    assert "Traceback (most recent call last):" not in result.stderr


def test_calculate_error_output_includes_traceback_with_debug() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            *_required_calculate_args(),
            "--training-zones",
            '{"1":',
            "--debug",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error: training_zones: invalid JSON" in result.stderr
    assert "Traceback (most recent call last):" in result.stderr
