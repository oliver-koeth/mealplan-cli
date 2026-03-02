"""Tests for domain invariant validation helpers."""

from __future__ import annotations

from typing import cast

import pytest

from mealplan.domain.enums import MealName
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation
from mealplan.domain.validation import (
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_validate_macro_targets_invariants_accepts_non_negative_values() -> None:
    """Non-negative macro targets should satisfy domain invariants."""
    validate_macro_targets_invariants(MacroTargets(protein_g=145.0, carbs_g=290.0, fat_g=70.0))


@pytest.mark.parametrize(
    ("macro_targets", "expected_message"),
    [
        (
            MacroTargets(protein_g=-1.0, carbs_g=290.0, fat_g=70.0),
            "macro_targets.protein_g: must be greater than or equal to 0",
        ),
        (
            MacroTargets(protein_g=145.0, carbs_g=-0.01, fat_g=70.0),
            "macro_targets.carbs_g: must be greater than or equal to 0",
        ),
        (
            MacroTargets(protein_g=145.0, carbs_g=290.0, fat_g=-0.1),
            "macro_targets.fat_g: must be greater than or equal to 0",
        ),
    ],
)
def test_validate_macro_targets_invariants_rejects_negative_values(
    macro_targets: MacroTargets,
    expected_message: str,
) -> None:
    """Negative macro targets should map to deterministic domain rule failures."""
    with pytest.raises(DomainRuleError) as error_info:
        validate_macro_targets_invariants(macro_targets)

    assert str(error_info.value) == expected_message
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def test_validate_macro_targets_negative_fat_is_not_validation_error() -> None:
    """Negative-fat outcomes must be classified as domain errors, not input validation."""
    with pytest.raises(DomainRuleError) as error_info:
        validate_macro_targets_invariants(MacroTargets(protein_g=120.0, carbs_g=250.0, fat_g=-1.0))

    assert not isinstance(error_info.value, ValidationError)


def test_validate_meal_allocation_invariants_accepts_canonical_shape() -> None:
    """Canonical six-meal allocation shape should satisfy domain invariants."""
    validate_meal_allocation_invariants(_build_canonical_meal_allocations())


def test_validate_meal_allocation_invariants_rejects_wrong_count() -> None:
    """Meal allocations must include exactly six entries."""
    meal_allocations = _build_canonical_meal_allocations()[:-1]

    with pytest.raises(DomainRuleError) as error_info:
        validate_meal_allocation_invariants(meal_allocations)

    assert str(error_info.value) == "meal_allocations: expected exactly 6 meals, got 5"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def test_validate_meal_allocation_invariants_rejects_duplicate_meal_names() -> None:
    """Duplicate canonical meal names should fail invariant validation."""
    meal_allocations = _build_canonical_meal_allocations()
    meal_allocations[-1] = MealAllocation(
        meal=MealName.BREAKFAST,
        carbs_g=meal_allocations[-1].carbs_g,
        protein_g=meal_allocations[-1].protein_g,
        fat_g=meal_allocations[-1].fat_g,
    )

    with pytest.raises(DomainRuleError) as error_info:
        validate_meal_allocation_invariants(meal_allocations)

    assert str(error_info.value) == "meal_allocations: duplicate meal names: breakfast"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def test_validate_meal_allocation_invariants_rejects_missing_canonical_meal() -> None:
    """Missing canonical meal coverage should fail invariant validation."""
    meal_allocations = _build_canonical_meal_allocations()
    meal_allocations[-1] = MealAllocation(
        meal=cast(MealName, "late-snack"),
        carbs_g=meal_allocations[-1].carbs_g,
        protein_g=meal_allocations[-1].protein_g,
        fat_g=meal_allocations[-1].fat_g,
    )

    with pytest.raises(DomainRuleError) as error_info:
        validate_meal_allocation_invariants(meal_allocations)

    assert str(error_info.value) == "meal_allocations: missing meal names: evening-snack"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def test_validate_meal_allocation_invariants_rejects_out_of_order_sequence() -> None:
    """Canonical meal coverage still requires canonical ordering."""
    meal_allocations = _build_canonical_meal_allocations()
    meal_allocations[0], meal_allocations[1] = meal_allocations[1], meal_allocations[0]

    with pytest.raises(DomainRuleError) as error_info:
        validate_meal_allocation_invariants(meal_allocations)

    assert (
        str(error_info.value) == "meal_allocations: meals must match canonical meal order exactly"
    )
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def _build_canonical_meal_allocations() -> list[MealAllocation]:
    return [
        MealAllocation(meal=meal, carbs_g=50.0, protein_g=25.0, fat_g=10.0)
        for meal in CANONICAL_MEAL_ORDER
    ]
