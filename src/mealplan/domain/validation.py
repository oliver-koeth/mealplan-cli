"""Domain invariant validation helpers."""

from __future__ import annotations

from collections import Counter

from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation
from mealplan.shared.errors import DomainRuleError

CARB_RECONCILIATION_TOLERANCE = 1e-9


def validate_macro_targets_invariants(macro_targets: MacroTargets) -> None:
    """Enforce hard non-negative invariants for macro-target aggregates."""
    _ensure_non_negative("protein_g", macro_targets.protein_g)
    _ensure_non_negative("carbs_g", macro_targets.carbs_g)
    _ensure_non_negative("fat_g", macro_targets.fat_g)


def validate_meal_allocation_invariants(meal_allocations: list[MealAllocation]) -> None:
    """Enforce canonical six-meal shape, coverage, and ordering invariants."""
    if len(meal_allocations) != len(CANONICAL_MEAL_ORDER):
        raise DomainRuleError(
            f"meal_allocations: expected exactly {len(CANONICAL_MEAL_ORDER)} meals, "
            f"got {len(meal_allocations)}"
        )

    meal_sequence = [allocation.meal for allocation in meal_allocations]
    counts = Counter(meal_sequence)
    duplicate_meals = [meal for meal in CANONICAL_MEAL_ORDER if counts[meal] > 1]
    missing_meals = [meal for meal in CANONICAL_MEAL_ORDER if counts[meal] == 0]
    if duplicate_meals:
        duplicates = ", ".join(meal.value for meal in duplicate_meals)
        raise DomainRuleError(f"meal_allocations: duplicate meal names: {duplicates}")
    if missing_meals:
        missing = ", ".join(meal.value for meal in missing_meals)
        raise DomainRuleError(f"meal_allocations: missing meal names: {missing}")

    if meal_sequence != list(CANONICAL_MEAL_ORDER):
        raise DomainRuleError("meal_allocations: meals must match canonical meal order exactly")


def validate_carb_reconciliation_invariants(
    macro_targets: MacroTargets,
    meal_allocations: list[MealAllocation],
) -> None:
    """Enforce deterministic reconciliation between target carbs and meal-level carbs."""
    meal_carbs_sum = sum(allocation.carbs_g for allocation in meal_allocations)
    delta = abs(meal_carbs_sum - macro_targets.carbs_g)
    if delta > CARB_RECONCILIATION_TOLERANCE:
        raise DomainRuleError(
            "carb_reconciliation: "
            f"sum(meal_allocations.carbs_g)={meal_carbs_sum} "
            f"differs from macro_targets.carbs_g={macro_targets.carbs_g} "
            f"(delta={delta}, tolerance={CARB_RECONCILIATION_TOLERANCE})"
        )


def _ensure_non_negative(field: str, value: float) -> None:
    if value < 0:
        raise DomainRuleError(f"macro_targets.{field}: must be greater than or equal to 0")
