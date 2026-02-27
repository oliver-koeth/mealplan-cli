"""CLI tests for deterministic placeholder command output."""

from __future__ import annotations

import subprocess
import sys


def test_probe_command_returns_deterministic_output() -> None:
    """`python -m mealplan probe` should return the placeholder message."""
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "probe"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "mealplan stub: ready"
