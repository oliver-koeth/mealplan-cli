"""Tests for application boundary contract scaffolding."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import (
    CONTRACT_UNITS_POLICY,
    MealPlanRequest,
    MealPlanResponse,
    ProbeRequest,
    ProbeResponse,
)


def _assert_validation_error_types(
    error: PydanticValidationError,
    expected_types: set[str],
) -> None:
    """Assert pydantic errors contain at least one expected stable error category."""
    actual_types = {detail["type"] for detail in error.errors()}
    assert actual_types.intersection(expected_types)


def test_meal_plan_request_parses_canonical_payload(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Request DTO should parse the canonical schema shape without coercion."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)

    assert request.age == 35
    assert request.weight_kg == 72.5
    assert request.training_session.zones_minutes["2"] == 40
    assert request.training_session.training_before_meal == "lunch"


def test_meal_plan_request_allows_missing_training_session(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """training_session is optional at schema-validation boundary."""
    payload = meal_plan_request_payload
    payload.pop("training_session")

    request = MealPlanRequest.model_validate(payload)
    assert request.training_session is None


def test_meal_plan_request_allows_missing_training_before_meal(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Schema should allow missing training_before_meal; semantic checks are deferred."""
    payload = meal_plan_request_payload
    payload["training_session"] = {
        "zones_minutes": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
    }

    request = MealPlanRequest.model_validate(payload)
    assert request.training_session is not None
    assert request.training_session.training_before_meal is None


@pytest.mark.parametrize(
    ("missing_field", "expected_error_types"),
    [
        ("age", {"missing"}),
        ("gender", {"missing"}),
        ("weight_kg", {"missing"}),
        ("activity_level", {"missing"}),
        ("carb_mode", {"missing"}),
        ("training_load_tomorrow", {"missing"}),
    ],
)
def test_meal_plan_request_rejects_missing_required_fields(
    meal_plan_request_payload: dict[str, Any],
    missing_field: str,
    expected_error_types: set[str],
) -> None:
    """Request DTO should fail when required top-level fields are omitted."""
    payload = meal_plan_request_payload
    payload.pop(missing_field)

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanRequest.model_validate(payload)

    _assert_validation_error_types(error_info.value, expected_error_types)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("gender", "other"),
        ("activity_level", "extreme"),
        ("carb_mode", "keto"),
        ("training_load_tomorrow", "peak"),
    ],
)
def test_meal_plan_request_rejects_invalid_enum_values(
    meal_plan_request_payload: dict[str, Any],
    field: str,
    invalid_value: str,
) -> None:
    """Request enum fields should reject out-of-domain string values."""
    payload = meal_plan_request_payload
    payload[field] = invalid_value

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanRequest.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"enum"})


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_error_types"),
    [
        ("age", "35", {"int_type"}),
        ("weight_kg", "72.5", {"float_type"}),
        ("training_session", "not-an-object", {"model_type", "model_attributes_type"}),
    ],
)
def test_meal_plan_request_rejects_invalid_primitive_and_nested_types(
    meal_plan_request_payload: dict[str, Any],
    field: str,
    invalid_value: Any,
    expected_error_types: set[str],
) -> None:
    """Request DTO should reject numeric strings and malformed nested structures."""
    payload = meal_plan_request_payload
    payload[field] = invalid_value

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanRequest.model_validate(payload)

    _assert_validation_error_types(error_info.value, expected_error_types)


@pytest.mark.parametrize(
    "zones_minutes",
    [
        {"6": 10},
        {"0": 10},
        {"1": "20", "2": 10, "3": 0, "4": 0, "5": 0},
    ],
)
def test_meal_plan_request_rejects_invalid_zones_minutes_matrix(
    meal_plan_request_payload: dict[str, Any],
    zones_minutes: dict[str, Any],
) -> None:
    """zones_minutes should reject out-of-range keys and invalid minute value types."""
    payload = meal_plan_request_payload
    payload["training_session"] = {
        "zones_minutes": zones_minutes,
        "training_before_meal": "lunch",
    }

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanRequest.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"literal_error", "int_type"})


def test_meal_plan_response_serializes_full_contract_shape(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    """Response DTO should preserve exact top-level and nested keys."""
    response = MealPlanResponse.model_validate(meal_plan_response_payload)

    assert response.model_dump() == meal_plan_response_payload


def test_meal_plan_response_requires_canonical_meal_order(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    """Meals must follow the canonical ordering contract."""
    payload = meal_plan_response_payload
    payload["meals"] = [payload["meals"][1], payload["meals"][0], *payload["meals"][2:]]

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"value_error"})


@pytest.mark.parametrize(
    "missing_field",
    ["TDEE", "training_carbs_g", "protein_g", "carbs_g", "fat_g", "meals"],
)
def test_meal_plan_response_rejects_missing_required_fields(
    meal_plan_response_payload: dict[str, Any],
    missing_field: str,
) -> None:
    """Response DTO should fail when required top-level fields are omitted."""
    payload = meal_plan_response_payload
    payload.pop(missing_field)

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"missing"})


@pytest.mark.parametrize(
    "invalid_value",
    ["2400.0", "not-a-number"],
)
def test_meal_plan_response_rejects_numeric_strings_for_tdee(
    meal_plan_response_payload: dict[str, Any],
    invalid_value: str,
) -> None:
    """Response numeric fields should reject string values under strict typing."""
    payload = meal_plan_response_payload
    payload["TDEE"] = invalid_value

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"float_type"})


@pytest.mark.parametrize(
    "invalid_meals",
    [
        "not-a-list",
        [{"meal": "breakfast", "carbs_g": 10.0, "protein_g": 5.0}],
        [{"meal": "breakfast", "carbs_g": 10.0, "protein_g": 5.0, "fat_g": 2.0}] * 6,
    ],
)
def test_meal_plan_response_rejects_malformed_meals_shape(
    meal_plan_response_payload: dict[str, Any],
    invalid_meals: Any,
) -> None:
    """Response DTO should reject malformed meals collection and item shapes."""
    payload = meal_plan_response_payload
    payload["meals"] = invalid_meals

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(
        error_info.value,
        {"list_type", "missing", "value_error", "enum"},
    )


def test_meal_plan_response_json_serialization_is_deterministic(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    """Equivalent models should produce byte-identical JSON output."""
    payload = meal_plan_response_payload
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
    with pytest.raises(PydanticValidationError):
        ProbeRequest.model_validate({"simulate_error": None, "unexpected": "x"})
