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
