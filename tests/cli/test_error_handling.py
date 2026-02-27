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
