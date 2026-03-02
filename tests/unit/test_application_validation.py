"""Tests for application-level semantic validation rules."""

from __future__ import annotations

from typing import Any

import pytest

from mealplan.application.contracts import MealPlanRequest
from mealplan.application.validation import validate_semantic_input
from mealplan.shared.errors import ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_validate_semantic_input_accepts_canonical_payload(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Canonical parsed request should pass semantic guards."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)

    validate_semantic_input(request)


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("age", 0, "age: must be greater than 0"),
        ("age", -1, "age: must be greater than 0"),
        ("weight_kg", 0.0, "weight_kg: must be greater than 0"),
        ("weight_kg", -0.5, "weight_kg: must be greater than 0"),
    ],
)
def test_validate_semantic_input_rejects_non_positive_values(
    meal_plan_request_payload: dict[str, Any],
    field: str,
    value: int | float,
    expected_message: str,
) -> None:
    """Semantic validator should raise shared ValidationError for non-positive inputs."""
    payload = meal_plan_request_payload
    payload[field] = value
    request = MealPlanRequest.model_validate(payload)

    with pytest.raises(ValidationError) as error_info:
        validate_semantic_input(request)

    assert str(error_info.value) == expected_message
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION


def test_validate_semantic_input_error_payload_is_deterministic(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Repeated semantic failures should produce stable validation payload text."""
    payload = meal_plan_request_payload
    payload["age"] = 0
    request = MealPlanRequest.model_validate(payload)

    messages: list[str] = []
    for _ in range(2):
        with pytest.raises(ValidationError) as error_info:
            validate_semantic_input(request)
        messages.append(str(error_info.value))

    assert messages[0] == messages[1]


@pytest.mark.parametrize(
    ("zones_minutes", "training_before_meal", "expected_message"),
    [
        ({"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}, None, None),
        (
            {"1": 1, "2": 0, "3": 0, "4": 0, "5": 0},
            None,
            "training_session.training_before_meal: required when total zones_minutes > 0",
        ),
    ],
)
def test_validate_semantic_input_training_before_meal_dependency(
    meal_plan_request_payload: dict[str, Any],
    zones_minutes: dict[str, int],
    training_before_meal: str | None,
    expected_message: str | None,
) -> None:
    """Training meal dependency should only apply when there is training volume."""
    payload = meal_plan_request_payload
    payload["training_session"] = {
        "zones_minutes": zones_minutes,
        "training_before_meal": training_before_meal,
    }
    request = MealPlanRequest.model_validate(payload)

    if expected_message is None:
        validate_semantic_input(request)
        return

    with pytest.raises(ValidationError) as error_info:
        validate_semantic_input(request)
    assert str(error_info.value) == expected_message
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION
