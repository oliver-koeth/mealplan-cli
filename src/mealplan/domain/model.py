"""Canonical domain model constants shared across layers."""

from __future__ import annotations

from mealplan.domain.enums import MealName

# Fixed meal ordering used by allocation and serialization pathways.
CANONICAL_MEAL_ORDER: tuple[MealName, MealName, MealName, MealName, MealName, MealName] = (
    MealName.BREAKFAST,
    MealName.MORNING_SNACK,
    MealName.LUNCH,
    MealName.AFTERNOON_SNACK,
    MealName.DINNER,
    MealName.EVENING_SNACK,
)

