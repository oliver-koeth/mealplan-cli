"""Tests for mapping contract parse failures to shared validation errors."""

from __future__ import annotations

from typing import Any

from mealplan.application.contracts import MealPlanRequest, ProbeRequest
from mealplan.application.parsing import parse_contract
from mealplan.shared.errors import ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_parse_contract_maps_pydantic_failure_to_validation_error() -> None:
    """Parse failures should raise shared ValidationError with field path detail."""
    try:
        parse_contract(
            ProbeRequest,
            {"simulate_error": None, "unexpected": "x"},
        )
    except ValidationError as error:
        assert "unexpected" in str(error)
        assert "Extra inputs are not permitted" in str(error)
        assert map_exception_to_exit_code(error) is ExitCode.VALIDATION
    else:
        raise AssertionError("Expected parse failure to map to ValidationError.")


def test_parse_contract_error_message_is_deterministic_for_nested_paths(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Repeated invalid payloads should produce stable mapped validation messages."""
    payload = meal_plan_request_payload
    payload["training_session"] = {
        "zones_minutes": {"6": 10},
        "training_before_meal": "lunch",
    }

    errors: list[str] = []
    for _ in range(2):
        try:
            parse_contract(MealPlanRequest, payload)
        except ValidationError as error:
            errors.append(str(error))
        else:
            raise AssertionError("Expected parse failure for invalid zone key.")

    assert errors[0] == errors[1]
    assert "training_session.zones_minutes" in errors[0]
