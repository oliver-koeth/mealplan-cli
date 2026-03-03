"""Composed domain service entrypoints."""

from __future__ import annotations

from collections.abc import Mapping

from mealplan.domain.energy import tdee_kcal_per_day_for
from mealplan.domain.enums import CarbMode, MealName, TrainingLoadTomorrow
from mealplan.domain.macros import carbs_target_g_for, fat_target_g_for, protein_target_g_for
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, UserProfile


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

    Phase 6 Story US-001 establishes the typed domain API and output contract.
    Story US-002 adds the post-training two-high-meal selection rule.
    """
    del carb_mode, training_load_tomorrow
    per_meal_carbs_g = daily_carbs_g / float(len(CANONICAL_MEAL_ORDER))
    allocation = dict.fromkeys(CANONICAL_MEAL_ORDER, per_meal_carbs_g)

    if training_before_meal is None:
        return allocation

    high_meal_carbs_g = 0.30 * daily_carbs_g
    first_high_meal_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
    second_high_meal_idx = (first_high_meal_idx + 1) % len(CANONICAL_MEAL_ORDER)
    first_high_meal = CANONICAL_MEAL_ORDER[first_high_meal_idx]
    second_high_meal = CANONICAL_MEAL_ORDER[second_high_meal_idx]
    high_meals = {first_high_meal, second_high_meal}

    allocation[first_high_meal] = high_meal_carbs_g
    allocation[second_high_meal] = high_meal_carbs_g

    remaining_carbs_g = daily_carbs_g - (2.0 * high_meal_carbs_g)
    low_meal_carbs_g = remaining_carbs_g / float(len(CANONICAL_MEAL_ORDER) - len(high_meals))
    for meal in CANONICAL_MEAL_ORDER:
        if meal in high_meals:
            continue
        allocation[meal] = low_meal_carbs_g
    return allocation
