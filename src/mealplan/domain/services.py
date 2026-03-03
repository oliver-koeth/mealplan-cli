"""Composed domain service entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict

from mealplan.domain.energy import tdee_kcal_per_day_for
from mealplan.domain.enums import CarbMode, MealName, TrainingLoadTomorrow
from mealplan.domain.macros import carbs_target_g_for, fat_target_g_for, protein_target_g_for
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation, UserProfile
from mealplan.domain.validation import validate_meal_allocation_invariants
from mealplan.shared.errors import DomainRuleError

CARB_RECONCILIATION_TOLERANCE = 1e-9
MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE = 1e-9
MacroField = Literal["carbs_g", "protein_g", "fat_g"]
MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER: tuple[MacroField, MacroField, MacroField] = (
    "carbs_g",
    "protein_g",
    "fat_g",
)


class MealPayloadRow(TypedDict):
    meal: MealName
    carbs_g: float
    protein_g: float
    fat_g: float


def calculate_tdee_kcal(profile: UserProfile) -> float:
    """Return canonical daily energy expenditure for a typed user profile."""
    return tdee_kcal_per_day_for(profile)


def calculate_macro_targets(
    *,
    profile: UserProfile,
    carb_mode: CarbMode,
    tdee_kcal: float,
) -> MacroTargets:
    """Return canonical macro targets derived from profile, mode, and TDEE."""
    protein_g = protein_target_g_for(profile.weight_kg)
    carbs_g = carbs_target_g_for(weight_kg=profile.weight_kg, carb_mode=carb_mode)
    fat_g = fat_target_g_for(tdee_kcal=tdee_kcal, protein_g=protein_g, carbs_g=carbs_g)
    return MacroTargets(protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g)


def calculate_training_carbs_g(zones_minutes: Mapping[int, int]) -> float:
    """Return deterministic training fueling carbs as float from normalized zone minutes.

    Contract:
    - Accepts normalized canonical zone keys ``1..5`` with integer minute values.
    - Returns a ``float`` for every valid input.
    - Is pure/deterministic: identical inputs always produce identical outputs.
    """
    total_minutes = sum(zones_minutes.values())
    if total_minutes == 0:
        return 0.0

    if all(minutes == 0 for zone, minutes in zones_minutes.items() if zone != 1):
        return 0.0

    return float(total_minutes)


def calculate_periodized_carb_allocation(
    carb_mode: CarbMode,
    daily_carbs_g: float,
    training_before_meal: MealName | None,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> dict[MealName, float]:
    """Return deterministic canonical six-meal carb allocation for Phase 6 entrypoint.

    Phase 6 note:
    - ``LOW`` and ``NORMAL`` carb modes intentionally bypass redistribution rules.
    - Bypass semantics are a temporary placeholder until Phase 7 meal assembly.
    """
    # 1) Non-periodized bypass: return deterministic equal split.
    if carb_mode is not CarbMode.PERIODIZED:
        allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
        _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
        return allocation

    if training_before_meal is None:
        allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
        _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
        return allocation

    # 2) Post-training high-meal rule.
    high_meals = _post_training_high_meals(training_before_meal=training_before_meal)

    # 3) Next-day high-load override, unless explicit conflict.
    high_meals = _apply_tomorrow_high_override(
        high_meals=high_meals,
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
    )

    allocation = _allocation_for_high_meals(
        daily_carbs_g=daily_carbs_g,
        high_meals=high_meals,
    )

    # 4) Reconciliation check.
    _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
    return allocation


def calculate_meal_split_and_response_payload(
    tdee_kcal: float,
    training_carbs_g: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    carb_allocation_g_by_meal: Mapping[MealName, float],
) -> dict[str, object]:
    """Return canonical response payload from top-level targets and meal carb allocation."""
    _validate_carb_allocation_keys(carb_allocation_g_by_meal=carb_allocation_g_by_meal)

    per_meal_protein_g = protein_g / float(len(CANONICAL_MEAL_ORDER))
    per_meal_fat_g = fat_g / float(len(CANONICAL_MEAL_ORDER))

    meal_allocations = [
        MealAllocation(
            meal=meal,
            carbs_g=carb_allocation_g_by_meal[meal],
            protein_g=per_meal_protein_g,
            fat_g=per_meal_fat_g,
        )
        for meal in CANONICAL_MEAL_ORDER
    ]
    validate_meal_allocation_invariants(meal_allocations)

    meals: list[MealPayloadRow] = [
        {
            "meal": allocation.meal,
            "carbs_g": round(allocation.carbs_g, 2),
            "protein_g": round(allocation.protein_g, 2),
            "fat_g": round(allocation.fat_g, 2),
        }
        for allocation in meal_allocations
    ]
    _reconcile_rounded_meal_totals(
        meals=meals,
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
    )

    return {
        "TDEE": tdee_kcal,
        "training_carbs_g": training_carbs_g,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "meals": meals,
    }


def _reconcile_rounded_meal_totals(
    *,
    meals: list[MealPayloadRow],
    carbs_g: float,
    protein_g: float,
    fat_g: float,
) -> None:
    targets: dict[MacroField, float] = {
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
    }
    evening_snack = _get_evening_snack_meal(meals=meals)

    for macro in MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER:
        rounded_total = sum(float(meal[macro]) for meal in meals)
        residual = round(targets[macro] - rounded_total, 2)
        if residual != 0.0:
            evening_snack[macro] = round(float(evening_snack[macro]) + residual, 2)

    for macro in MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER:
        reconciled_total = sum(float(meal[macro]) for meal in meals)
        delta = abs(reconciled_total - targets[macro])
        if delta > MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE:
            raise DomainRuleError(
                "meal_assembly.reconciliation: "
                f"sum(meals.{macro})={reconciled_total} "
                f"differs from target={targets[macro]} "
                f"(delta={delta}, tolerance={MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE})"
            )


def _get_evening_snack_meal(*, meals: list[MealPayloadRow]) -> MealPayloadRow:
    for meal in meals:
        if meal["meal"] is MealName.EVENING_SNACK:
            return meal
    raise DomainRuleError("meal_assembly.reconciliation: missing evening-snack meal")


def _validate_carb_allocation_keys(
    *,
    carb_allocation_g_by_meal: Mapping[MealName, float],
) -> None:
    canonical_meal_set = set(CANONICAL_MEAL_ORDER)
    provided_meal_set = set(carb_allocation_g_by_meal.keys())
    if provided_meal_set == canonical_meal_set:
        return

    missing_meals = [
        canonical_meal.value
        for canonical_meal in CANONICAL_MEAL_ORDER
        if canonical_meal not in provided_meal_set
    ]
    extra_meals = sorted(
        _meal_key_label(meal_key)
        for meal_key in provided_meal_set
        if meal_key not in canonical_meal_set
    )
    raise DomainRuleError(
        "meal_assembly.carb_allocation: "
        f"missing={missing_meals}, extra={extra_meals}"
    )


def _meal_key_label(meal_key: object) -> str:
    if isinstance(meal_key, MealName):
        return meal_key.value
    return repr(meal_key)


def _equal_split_allocation(*, daily_carbs_g: float) -> dict[MealName, float]:
    per_meal_carbs_g = daily_carbs_g / float(len(CANONICAL_MEAL_ORDER))
    return dict.fromkeys(CANONICAL_MEAL_ORDER, per_meal_carbs_g)


def _post_training_high_meals(*, training_before_meal: MealName) -> set[MealName]:
    first_high_meal_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
    second_high_meal_idx = (first_high_meal_idx + 1) % len(CANONICAL_MEAL_ORDER)
    return {
        CANONICAL_MEAL_ORDER[first_high_meal_idx],
        CANONICAL_MEAL_ORDER[second_high_meal_idx],
    }


def _apply_tomorrow_high_override(
    *,
    high_meals: set[MealName],
    training_before_meal: MealName,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> set[MealName]:
    conflict_with_tomorrow_high_override = training_before_meal in {
        MealName.DINNER,
        MealName.EVENING_SNACK,
    }
    if (
        training_load_tomorrow == TrainingLoadTomorrow.HIGH
        and not conflict_with_tomorrow_high_override
    ):
        return (high_meals | {MealName.DINNER}) - {MealName.EVENING_SNACK}
    return high_meals


def _allocation_for_high_meals(
    *,
    daily_carbs_g: float,
    high_meals: set[MealName],
) -> dict[MealName, float]:
    allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
    high_meal_carbs_g = 0.30 * daily_carbs_g

    for high_meal in high_meals:
        allocation[high_meal] = high_meal_carbs_g

    remaining_carbs_g = daily_carbs_g - (float(len(high_meals)) * high_meal_carbs_g)
    low_meal_carbs_g = remaining_carbs_g / float(len(CANONICAL_MEAL_ORDER) - len(high_meals))
    for meal in CANONICAL_MEAL_ORDER:
        if meal not in high_meals:
            allocation[meal] = low_meal_carbs_g
    return allocation


def _validate_carb_reconciliation(
    *,
    allocation: dict[MealName, float],
    daily_carbs_g: float,
) -> None:
    total_allocated_carbs = sum(allocation.values())
    delta = abs(total_allocated_carbs - daily_carbs_g)
    if delta > CARB_RECONCILIATION_TOLERANCE:
        raise DomainRuleError(
            "carb_reconciliation: "
            f"sum(allocated_carbs)={total_allocated_carbs} "
            f"differs from daily_carbs_g={daily_carbs_g} "
            f"(delta={delta}, tolerance={CARB_RECONCILIATION_TOLERANCE})"
        )
