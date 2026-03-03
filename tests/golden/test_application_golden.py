"""Golden snapshot regression tests for application calculation responses."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mealplan.application.contracts import MealPlanRequest
from mealplan.application.orchestration import MealPlanCalculationService
from tests.golden.helpers import (
    assert_hybrid_snapshot_match,
    load_golden_json,
    to_canonical_json_object,
)

_GOLDEN_DIR = Path(__file__).parent / "application"
_BASE_REQUEST_PAYLOAD = {
    "age": 20,
    "gender": "male",
    "height_cm": 170,
    "weight_kg": 54.0,
    "activity_level": "low",
    "carb_mode": "periodized",
    "training_load_tomorrow": "high",
    "training_session": {
        "zones_minutes": {"1": 10, "2": 20, "3": 0, "4": 0, "5": 0},
        "training_before_meal": "lunch",
    },
}


@pytest.mark.parametrize(
    ("fixture_name", "request_payload"),
    [
        ("periodized_with_training.golden.json", _BASE_REQUEST_PAYLOAD),
        (
            "non_periodized_with_training.golden.json",
            {**deepcopy(_BASE_REQUEST_PAYLOAD), "carb_mode": "normal"},
        ),
        (
            "periodized_without_training.golden.json",
            {**deepcopy(_BASE_REQUEST_PAYLOAD), "training_session": None},
        ),
    ],
)
def test_application_calculate_matches_golden_snapshots(
    fixture_name: str,
    request_payload: dict[str, object],
) -> None:
    service = MealPlanCalculationService()
    request = MealPlanRequest.model_validate(request_payload)

    response = service.calculate(request)

    expected = to_canonical_json_object(load_golden_json(_GOLDEN_DIR / fixture_name))
    actual = to_canonical_json_object(response.model_dump(mode="json"))
    assert_hybrid_snapshot_match(actual, expected)
