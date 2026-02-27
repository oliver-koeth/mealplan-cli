"""Tests for application boundary contract scaffolding."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import MealPlanRequest, ProbeRequest, ProbeResponse


def _valid_request_payload() -> dict[str, Any]:
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


def test_meal_plan_request_parses_canonical_payload() -> None:
    """Request DTO should parse the canonical schema shape without coercion."""
    request = MealPlanRequest.model_validate(_valid_request_payload())

    assert request.age == 35
    assert request.weight_kg == 72.5
    assert request.training_session.zones_minutes["2"] == 40
    assert request.training_session.training_before_meal == "lunch"


def test_meal_plan_request_rejects_unknown_fields_at_root() -> None:
    """Unknown fields must be rejected at request root."""
    payload = _valid_request_payload()
    payload["unexpected"] = "x"

    try:
        MealPlanRequest.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected unknown root field validation to fail.")


def test_meal_plan_request_rejects_unknown_fields_in_training_session() -> None:
    """Unknown fields must also be rejected for nested contracts."""
    payload = _valid_request_payload()
    training_session = dict(payload["training_session"])
    training_session["unexpected"] = "x"
    payload["training_session"] = training_session

    try:
        MealPlanRequest.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected unknown nested field validation to fail.")


def test_meal_plan_request_rejects_numeric_strings() -> None:
    """Strict numeric fields should reject string input instead of coercing."""
    payload = _valid_request_payload()
    payload["age"] = "35"

    try:
        MealPlanRequest.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected strict numeric validation to reject strings.")


def test_probe_request_parses_known_payload() -> None:
    """Request model should accept the placeholder error field shape."""
    request = ProbeRequest.model_validate({"simulate_error": "validation"})
    assert request.simulate_error == "validation"


def test_probe_response_serializes_known_payload() -> None:
    """Response model should serialize the placeholder message field."""
    response = ProbeResponse(message="mealplan stub: ready")
    assert response.model_dump() == {"message": "mealplan stub: ready"}


def test_probe_request_rejects_unknown_fields() -> None:
    """Boundary models should fail when unexpected keys are provided."""
    try:
        ProbeRequest.model_validate({"simulate_error": None, "unexpected": "x"})
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected unknown field validation to fail.")
