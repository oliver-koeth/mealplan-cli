"""Golden snapshot regression tests for application calculation responses."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mealplan.application.contracts import MealPlanRequest
from mealplan.application.orchestration import MealPlanCalculationService

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


def _snapshot_payload(response: object) -> str:
    return json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _assert_golden_matches(*, fixture_name: str, actual: str) -> None:
    expected = (_GOLDEN_DIR / fixture_name).read_text(encoding="utf-8")
    assert actual == expected


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

    actual = _snapshot_payload(response.model_dump(mode="json"))
    _assert_golden_matches(fixture_name=fixture_name, actual=actual)
