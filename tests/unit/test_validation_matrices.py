"""Phase 3 matrix coverage for semantic and domain validation failures."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from mealplan.application.contracts import MealPlanRequest
from mealplan.application.validation import normalize_training_zones, validate_semantic_input
from mealplan.domain.enums import MealName
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation
from mealplan.domain.validation import (
    validate_carb_reconciliation_invariants,
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


@pytest.mark.parametrize(
    ("mutate_payload", "expected_prefix"),
    [
        pytest.param(lambda payload: payload.update({"age": 0}), "age:", id="age-non-positive"),
        pytest.param(
            lambda payload: payload.update({"weight_kg": 0.0}),
            "weight_kg:",
            id="weight-non-positive",
        ),
        pytest.param(
            lambda payload: payload.update(
                {
                    "training_session": {
                        "zones_minutes": {"1": 5},
                        "training_before_meal": None,
                    }
                }
            ),
            "training_session.training_before_meal:",
            id="training-dependency",
        ),
    ],
)
def test_semantic_validation_failure_matrix(
    meal_plan_request_payload: dict[str, Any],
    mutate_payload: Callable[[dict[str, Any]], None],
    expected_prefix: str,
) -> None:
    """Semantic input failures should consistently map to validation-category errors."""
    payload = deepcopy(meal_plan_request_payload)
    mutate_payload(payload)
    request = MealPlanRequest.model_validate(payload)

    with pytest.raises(ValidationError) as error_info:
        validate_semantic_input(request)

    assert str(error_info.value).startswith(expected_prefix)
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION


@pytest.mark.parametrize(
    ("zones_minutes", "expected_normalized"),
    [
        pytest.param(
            {"2": 30, "5": 15},
            {1: 0, 2: 30, 3: 0, 4: 0, 5: 15},
            id="subset-keys",
        ),
        pytest.param(
            {1: 10, "2": 20, 5: 0},
            {1: 10, 2: 20, 3: 0, 4: 0, 5: 0},
            id="mixed-int-and-string-keys",
        ),
    ],
)
def test_zone_normalization_matrix(
    zones_minutes: dict[object, object],
    expected_normalized: dict[int, int],
) -> None:
    """Zone normalization should deterministically canonicalize allowed input variants."""
    assert normalize_training_zones(zones_minutes) == expected_normalized


@pytest.mark.parametrize(
    ("zones_minutes", "expected_fragment"),
    [
        pytest.param({"6": 10}, "zone must be between 1 and 5", id="zone-above-range"),
        pytest.param({0: 10}, "zone must be between 1 and 5", id="zone-below-range"),
        pytest.param({"zone-2": 10}, "invalid zone key", id="zone-key-format"),
        pytest.param(
            {"3": -1},
            "minutes must be greater than or equal to 0",
            id="negative-minutes",
        ),
        pytest.param({"4": 1.5}, "minutes must be an integer", id="non-integer-minutes"),
    ],
)
def test_zone_validation_failure_matrix(
    zones_minutes: dict[object, object],
    expected_fragment: str,
) -> None:
    """Invalid zone payloads should consistently map to validation-category errors."""
    with pytest.raises(ValidationError) as error_info:
        normalize_training_zones(zones_minutes)

    assert "training_session.zones_minutes." in str(error_info.value)
    assert expected_fragment in str(error_info.value)
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION


@pytest.mark.parametrize(
    ("run_check", "expected_prefix"),
    [
        pytest.param(
            lambda: validate_macro_targets_invariants(
                MacroTargets(protein_g=150.0, carbs_g=300.0, fat_g=-0.1)
            ),
            "macro_targets.",
            id="negative-fat",
        ),
        pytest.param(
            lambda: validate_meal_allocation_invariants(_canonical_meal_allocations()[:-1]),
            "meal_allocations:",
            id="meal-count",
        ),
        pytest.param(
            lambda: validate_meal_allocation_invariants(_duplicate_meal_allocations()),
            "meal_allocations:",
            id="meal-uniqueness",
        ),
        pytest.param(
            lambda: validate_meal_allocation_invariants(_out_of_order_meal_allocations()),
            "meal_allocations:",
            id="meal-order",
        ),
        pytest.param(
            lambda: validate_carb_reconciliation_invariants(
                MacroTargets(protein_g=150.0, carbs_g=299.0, fat_g=75.0),
                _canonical_meal_allocations(),
            ),
            "carb_reconciliation:",
            id="carb-mismatch",
        ),
    ],
)
def test_domain_invariant_failure_matrix(
    run_check: Callable[[], None],
    expected_prefix: str,
) -> None:
    """Domain invariant failures should consistently map to domain-category errors."""
    with pytest.raises(DomainRuleError) as error_info:
        run_check()

    assert str(error_info.value).startswith(expected_prefix)
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def _canonical_meal_allocations() -> list[MealAllocation]:
    return [
        MealAllocation(meal=meal, carbs_g=50.0, protein_g=25.0, fat_g=10.0)
        for meal in CANONICAL_MEAL_ORDER
    ]


def _duplicate_meal_allocations() -> list[MealAllocation]:
    meal_allocations = _canonical_meal_allocations()
    meal_allocations[-1] = MealAllocation(
        meal=MealName.BREAKFAST,
        carbs_g=meal_allocations[-1].carbs_g,
        protein_g=meal_allocations[-1].protein_g,
        fat_g=meal_allocations[-1].fat_g,
    )
    return meal_allocations


def _out_of_order_meal_allocations() -> list[MealAllocation]:
    meal_allocations = _canonical_meal_allocations()
    meal_allocations[0], meal_allocations[1] = meal_allocations[1], meal_allocations[0]
    return meal_allocations
