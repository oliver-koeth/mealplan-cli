"""CLI smoke tests for the packaged entrypoint behavior."""

from __future__ import annotations

import subprocess
import sys


def test_module_help_exits_successfully() -> None:
    """`python -m mealplan --help` should be runnable and return help output."""
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Usage" in result.stdout
