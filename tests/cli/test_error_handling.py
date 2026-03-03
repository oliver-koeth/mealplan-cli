"""CLI tests for controlled error-to-exit-code handling."""

from __future__ import annotations

import subprocess
import sys


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
