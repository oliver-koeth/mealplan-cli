"""CLI integration tests for production calculation command wiring."""

from __future__ import annotations

import json
import subprocess
import sys


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
