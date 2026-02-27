"""Tests for application boundary contract scaffolding."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import (
    CONTRACT_UNITS_POLICY,
    MealPlanRequest,
    MealPlanResponse,
    ProbeRequest,
    ProbeResponse,
)


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


def _valid_response_payload() -> dict[str, Any]:
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


def test_meal_plan_request_parses_canonical_payload() -> None:
    """Request DTO should parse the canonical schema shape without coercion."""
    request = MealPlanRequest.model_validate(_valid_request_payload())

    assert request.age == 35
    assert request.weight_kg == 72.5
    assert request.training_session.zones_minutes["2"] == 40
    assert request.training_session.training_before_meal == "lunch"


def test_meal_plan_request_allows_missing_training_session() -> None:
    """training_session is optional at schema-validation boundary."""
    payload = _valid_request_payload()
    payload.pop("training_session")

    request = MealPlanRequest.model_validate(payload)
    assert request.training_session is None


def test_meal_plan_request_allows_missing_training_before_meal() -> None:
    """Schema should allow missing training_before_meal; semantic checks are deferred."""
    payload = _valid_request_payload()
    payload["training_session"] = {
        "zones_minutes": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
    }

    request = MealPlanRequest.model_validate(payload)
    assert request.training_session is not None
    assert request.training_session.training_before_meal is None


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


def test_meal_plan_request_rejects_out_of_domain_zone_keys() -> None:
    """zones_minutes keys must be restricted to '1' through '5'."""
    payload = _valid_request_payload()
    payload["training_session"] = {
        "zones_minutes": {"6": 10},
        "training_before_meal": "lunch",
    }

    try:
        MealPlanRequest.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected invalid zone key validation to fail.")


def test_meal_plan_request_rejects_non_integer_zone_minutes() -> None:
    """zones_minutes values must be strict integers."""
    payload = _valid_request_payload()
    payload["training_session"] = {
        "zones_minutes": {"1": "20"},
        "training_before_meal": "lunch",
    }

    try:
        MealPlanRequest.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected invalid minute value type validation to fail.")


def test_meal_plan_response_serializes_full_contract_shape() -> None:
    """Response DTO should preserve exact top-level and nested keys."""
    response = MealPlanResponse.model_validate(_valid_response_payload())

    assert response.model_dump() == _valid_response_payload()


def test_meal_plan_response_requires_canonical_meal_order() -> None:
    """Meals must follow the canonical ordering contract."""
    payload = _valid_response_payload()
    payload["meals"] = [payload["meals"][1], payload["meals"][0], *payload["meals"][2:]]

    try:
        MealPlanResponse.model_validate(payload)
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected out-of-order meals validation to fail.")


def test_meal_plan_response_json_serialization_is_deterministic() -> None:
    """Equivalent models should produce byte-identical JSON output."""
    payload = _valid_response_payload()
    left = MealPlanResponse.model_validate(payload)
    right = MealPlanResponse.model_validate(payload)

    assert left.model_dump_json() == right.model_dump_json()


def test_meal_plan_response_placeholder_instantiates_full_shape() -> None:
    """Placeholder response should be usable before calculation logic exists."""
    response = MealPlanResponse.placeholder()

    assert response.TDEE == 0.0
    assert [meal.meal for meal in response.meals] == [
        "breakfast",
        "morning-snack",
        "lunch",
        "afternoon-snack",
        "dinner",
        "evening-snack",
    ]


def test_contract_units_policy_covers_request_and_response_units() -> None:
    """Contract module should publish explicit units metadata and legacy notes."""
    assert CONTRACT_UNITS_POLICY == {
        "age": "years",
        "weight_kg": "kg",
        "zones_minutes": "minutes",
        "TDEE": "kcal/day (legacy field name retained for compatibility)",
        "training_carbs_g": "g",
        "protein_g": "g",
        "carbs_g": "g",
        "fat_g": "g",
    }

    assert MealPlanRequest.model_fields["age"].description == "Age in years."
    assert MealPlanResponse.model_fields["TDEE"].description is not None
    assert "kcal/day" in MealPlanResponse.model_fields["TDEE"].description


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
