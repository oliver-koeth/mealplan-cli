"""Shared canonical fixtures for contract boundary tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def meal_plan_request_payload() -> dict[str, Any]:
    """Canonical valid request payload with optional training_session populated."""
    return {
        "age": 35,
        "gender": "male",
        "weight_kg": 72.5,
        "activity_level": "medium",
        "carb_mode": "periodized",
        "training_load_tomorrow": "high",
        "training_session": {
            "zones_minutes": {"1": 20, "2": 40, "3": 0, "4": 0, "5": 0},
            "training_before_meal": "lunch",
        },
    }


@pytest.fixture
def meal_plan_response_payload() -> dict[str, Any]:
    """Canonical valid response payload with six meals in canonical order."""
    return {
        "TDEE": 2400.0,
        "training_carbs_g": 60.0,
        "protein_g": 150.0,
        "carbs_g": 280.0,
        "fat_g": 80.0,
        "meals": [
            {"meal": "breakfast", "carbs_g": 50.0, "protein_g": 25.0, "fat_g": 15.0},
            {"meal": "morning-snack", "carbs_g": 30.0, "protein_g": 15.0, "fat_g": 10.0},
            {"meal": "lunch", "carbs_g": 70.0, "protein_g": 35.0, "fat_g": 20.0},
            {"meal": "afternoon-snack", "carbs_g": 35.0, "protein_g": 15.0, "fat_g": 10.0},
            {"meal": "dinner", "carbs_g": 65.0, "protein_g": 40.0, "fat_g": 20.0},
            {"meal": "evening-snack", "carbs_g": 30.0, "protein_g": 20.0, "fat_g": 5.0},
        ],
    }
