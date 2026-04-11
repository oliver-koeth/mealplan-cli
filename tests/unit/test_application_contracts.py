"""Tests for application boundary contract scaffolding."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import (
    AUTH_ERROR_DEFAULTS,
    CONTRACT_UNITS_POLICY,
    USER_MANAGEMENT_ROUTES,
    USERS_ATTACH_TOKEN_ROUTE,
    USERS_EXCHANGE_TOKEN_ROUTE,
    USERS_REGISTER_ROUTE,
    ApiErrorEnvelope,
    FoodLogEntry,
    FoodLogSearchRequest,
    FoodLogUpsertRequest,
    MealPlanRequest,
    MealPlanResponse,
    ProbeRequest,
    ProbeResponse,
    UserAttachTokenRequest,
    UserAttachTokenResponse,
    UserExchangeTokenRequest,
    UserExchangeTokenResponse,
    UserRegisterRequest,
    UserRegisterResponse,
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
    assert request.height_cm == 178
    assert request.weight_kg == 72.5
    assert request.vo2max is None
    assert request.training_session.zones_minutes["2"] == 40
    assert request.training_session.training_before_meal == "lunch"


def test_meal_plan_request_accepts_optional_vo2max(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    payload = meal_plan_request_payload
    payload["vo2max"] = 58

    request = MealPlanRequest.model_validate(payload)

    assert request.vo2max == 58


@pytest.mark.parametrize("vo2max", [10, 100])
def test_meal_plan_request_accepts_vo2max_range_boundaries(
    meal_plan_request_payload: dict[str, Any],
    vo2max: int,
) -> None:
    payload = meal_plan_request_payload
    payload["vo2max"] = vo2max

    request = MealPlanRequest.model_validate(payload)

    assert request.vo2max == vo2max


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
        ("height_cm", {"missing"}),
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
        ("height_cm", "178", {"int_type"}),
        ("weight_kg", "72.5", {"float_type"}),
        ("vo2max", "58", {"int_type"}),
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


@pytest.mark.parametrize("vo2max", [9, 101])
def test_meal_plan_request_rejects_out_of_range_vo2max(
    meal_plan_request_payload: dict[str, Any],
    vo2max: int,
) -> None:
    payload = meal_plan_request_payload
    payload["vo2max"] = vo2max

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanRequest.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"greater_than_equal", "less_than_equal"})


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


def test_meal_plan_response_allows_optional_training_meal_between_canonical_meals(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    payload = meal_plan_response_payload
    payload["meals"] = [
        payload["meals"][0],
        payload["meals"][1],
        {
            "meal": "training",
            "carbs_strategy": "high",
            "carbs_g": 60.0,
            "protein_g": 0.0,
            "fat_g": 0.0,
            "kcal": 240.0,
        },
        *payload["meals"][2:],
    ]
    payload["total_kcal"] = 2680.0
    payload["training_kcal"] = 280.0

    response = MealPlanResponse.model_validate(payload)

    assert response.meals[2].meal == "training"


def test_meal_plan_response_rejects_noncanonical_order_even_with_training_meal(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    payload = meal_plan_response_payload
    payload["meals"] = [
        {
            "meal": "training",
            "carbs_strategy": "high",
            "carbs_g": 60.0,
            "protein_g": 0.0,
            "fat_g": 0.0,
            "kcal": 240.0,
        },
        payload["meals"][1],
        payload["meals"][0],
        *payload["meals"][2:],
    ]

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"value_error"})


def test_meal_plan_response_rejects_duplicate_training_meals(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    payload = meal_plan_response_payload
    payload["meals"].extend(
        [
            {
                "meal": "training",
                "carbs_strategy": "high",
                "carbs_g": 30.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "kcal": 120.0,
            },
            {
                "meal": "training",
                "carbs_strategy": "high",
                "carbs_g": 30.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "kcal": 120.0,
            },
        ]
    )

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"value_error"})


@pytest.mark.parametrize(
    "missing_field",
    ["TDEE", "training_kcal", "protein_g", "carbs_g", "fat_g", "total_kcal", "meals"],
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
    assert response.training_kcal == 0.0
    assert [meal.meal for meal in response.meals] == [
        "breakfast",
        "morning-snack",
        "lunch",
        "afternoon-snack",
        "dinner",
        "evening-snack",
    ]
    assert [meal.carbs_strategy for meal in response.meals] == ["low"] * 6


def test_food_log_upsert_request_parses_canonical_payload() -> None:
    request = FoodLogUpsertRequest.model_validate(
        {
            "date": "20260408",
            "meal": "lunch",
            "name": "Greek yogurt bowl",
            "kcal": 420.0,
            "carbs": 45.0,
            "fat": 11.0,
            "protein": 33.0,
            "fiber": 8.0,
        }
    )

    assert request.uuid is None
    assert request.quantity == 1.0
    assert request.date == "20260408"


def test_food_log_upsert_request_accepts_uuid_for_update_paths() -> None:
    request = FoodLogUpsertRequest.model_validate(
        {
            "uuid": "4c3e42af-8c83-4702-b580-c6412838ef35",
            "date": "20260408",
            "meal": "dinner",
            "name": "Salmon plate",
            "kcal": 560.0,
            "carbs": 32.0,
            "fat": 24.0,
            "protein": 46.0,
            "fiber": 6.0,
            "quantity": 1.5,
        }
    )

    assert request.uuid == "4c3e42af-8c83-4702-b580-c6412838ef35"
    assert request.quantity == 1.5


@pytest.mark.parametrize("invalid_date", ["2026-04-08", "2026048", "20260230"])
def test_food_log_models_reject_non_canonical_dates(invalid_date: str) -> None:
    with pytest.raises(PydanticValidationError) as upsert_error:
        FoodLogUpsertRequest.model_validate(
            {
                "date": invalid_date,
                "meal": "breakfast",
                "name": "Oats",
                "kcal": 300.0,
                "carbs": 40.0,
                "fat": 7.0,
                "protein": 12.0,
                "fiber": 5.0,
            }
        )
    _assert_validation_error_types(upsert_error.value, {"value_error"})

    with pytest.raises(PydanticValidationError) as search_error:
        FoodLogSearchRequest.model_validate({"date": invalid_date})
    _assert_validation_error_types(search_error.value, {"value_error"})

    with pytest.raises(PydanticValidationError) as entry_error:
        FoodLogEntry.model_validate(
            {
                "uuid": "a93f6d76-e0ef-4c6f-a33e-f08d4f96eb80",
                "date": invalid_date,
                "meal": "lunch",
                "name": "Chicken wrap",
                "kcal": 470.0,
                "carbs": 39.0,
                "fat": 16.0,
                "protein": 34.0,
                "fiber": 4.0,
            }
        )
    _assert_validation_error_types(entry_error.value, {"value_error"})


def test_food_log_search_request_supports_optional_filters() -> None:
    request = FoodLogSearchRequest.model_validate({"name": "yogurt", "meal": "lunch"})

    assert request.date is None
    assert request.name == "yogurt"
    assert request.meal == "lunch"


def test_food_log_entry_serializes_canonical_shape() -> None:
    entry = FoodLogEntry.model_validate(
        {
            "uuid": "a93f6d76-e0ef-4c6f-a33e-f08d4f96eb80",
            "date": "20260408",
            "meal": "lunch",
            "name": "Chicken wrap",
            "kcal": 470.0,
            "carbs": 39.0,
            "fat": 16.0,
            "protein": 34.0,
            "fiber": 4.0,
        }
    )

    assert entry.model_dump() == {
        "uuid": "a93f6d76-e0ef-4c6f-a33e-f08d4f96eb80",
        "date": "20260408",
        "meal": "lunch",
        "name": "Chicken wrap",
        "kcal": 470.0,
        "carbs": 39.0,
        "fat": 16.0,
        "protein": 34.0,
        "fiber": 4.0,
    }


def test_contract_units_policy_covers_request_and_response_units() -> None:
    """Contract module should publish explicit units metadata and legacy notes."""
    assert CONTRACT_UNITS_POLICY == {
        "age": "years",
        "height_cm": "cm",
        "weight_kg": "kg",
        "vo2max": "ml/kg/min",
        "zones_minutes": "minutes",
        "TDEE": "kcal/day (legacy field name retained for compatibility)",
        "training_kcal": "kcal",
        "protein_g": "g",
        "carbs_g": "g",
        "fat_g": "g",
        "total_kcal": "kcal",
        "kcal": "kcal",
        "carbs": "g",
        "fat": "g",
        "protein": "g",
        "fiber": "g",
    }

    assert MealPlanRequest.model_fields["age"].description == "Age in years."
    assert MealPlanResponse.model_fields["TDEE"].description is not None
    assert "kcal/day" in MealPlanResponse.model_fields["TDEE"].description
    assert MealPlanResponse.model_fields["training_kcal"].description is not None


def test_meal_plan_response_rejects_total_kcal_that_does_not_match_tdee_plus_training_kcal(
    meal_plan_response_payload: dict[str, Any],
) -> None:
    payload = meal_plan_response_payload
    payload["total_kcal"] = 2440.01

    with pytest.raises(PydanticValidationError) as error_info:
        MealPlanResponse.model_validate(payload)

    _assert_validation_error_types(error_info.value, {"value_error"})


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


def test_user_management_routes_match_canonical_contract() -> None:
    assert USERS_REGISTER_ROUTE == "/api/v1/users/register"
    assert USERS_ATTACH_TOKEN_ROUTE == "/api/v1/users/attach-token"
    assert USERS_EXCHANGE_TOKEN_ROUTE == "/api/v1/users/exchange-token"
    assert USER_MANAGEMENT_ROUTES == (
        "/api/v1/users/register",
        "/api/v1/users/attach-token",
        "/api/v1/users/exchange-token",
    )


def test_auth_error_defaults_match_canonical_status_matrix() -> None:
    assert AUTH_ERROR_DEFAULTS == {
        "auth_missing_token": {
            "status": 401,
            "message": "Authorization bearer token is required.",
            "retry_after_seconds": None,
        },
        "auth_invalid_token": {
            "status": 401,
            "message": "Authorization bearer token is invalid.",
            "retry_after_seconds": None,
        },
        "auth_token_email_mismatch": {
            "status": 403,
            "message": "Bearer token does not match the requested user email.",
            "retry_after_seconds": None,
        },
        "user_already_exists": {
            "status": 409,
            "message": "A user with the requested email already exists.",
            "retry_after_seconds": None,
        },
        "auth_rate_limited": {
            "status": 429,
            "message": "Authentication rate limit exceeded. Retry later.",
            "retry_after_seconds": 60,
        },
    }


def test_api_error_envelope_parses_canonical_shape() -> None:
    envelope = ApiErrorEnvelope.model_validate(
        {
            "error": {
                "code": "auth_invalid_token",
                "message": "Authorization bearer token is invalid.",
                "request_id": "trace-123",
                "details": [{"field": "authorization", "message": "invalid bearer token"}],
            }
        }
    )

    assert envelope.model_dump() == {
        "error": {
            "code": "auth_invalid_token",
            "message": "Authorization bearer token is invalid.",
            "request_id": "trace-123",
            "details": [{"message": "invalid bearer token", "field": "authorization"}],
        }
    }


def test_user_management_request_response_contracts_parse_expected_shapes() -> None:
    register_request = UserRegisterRequest.model_validate(
        {"email": "alex@example.com", "name": "Alex"}
    )
    register_response = UserRegisterResponse.model_validate(
        {
            "email": "alex@example.com",
            "name": "Alex",
            "token": "mpu_v1_abcdefghijklmnopqrstuvwxyz",
        }
    )
    attach_request = UserAttachTokenRequest.model_validate(
        {
            "email": "alex@example.com",
            "token": "mpu_v1_abcdefghijklmnopqrstuvwxyz",
        }
    )
    attach_response = UserAttachTokenResponse.model_validate(
        {"email": "alex@example.com", "name": "Alex"}
    )
    exchange_request = UserExchangeTokenRequest.model_validate(
        {"token": "mpu_v1_abcdefghijklmnopqrstuvwxyz"}
    )
    exchange_response = UserExchangeTokenResponse.model_validate(
        {"token": "mpu_v1_abcdefghijklmnopqrstuvwxyz_new"}
    )

    assert register_request.email == "alex@example.com"
    assert register_response.token.startswith("mpu_v1_")
    assert attach_request.email == "alex@example.com"
    assert attach_response.name == "Alex"
    assert exchange_request.token.startswith("mpu_v1_")
    assert exchange_response.token.startswith("mpu_v1_")
