"""Canonical domain model constants shared across layers."""

from __future__ import annotations

from dataclasses import dataclass

from mealplan.domain.enums import ActivityLevel, Gender, MealName

# Fixed meal ordering used by allocation and serialization pathways.
CANONICAL_MEAL_ORDER: tuple[MealName, MealName, MealName, MealName, MealName, MealName] = (
    MealName.BREAKFAST,
    MealName.MORNING_SNACK,
    MealName.LUNCH,
    MealName.AFTERNOON_SNACK,
    MealName.DINNER,
    MealName.EVENING_SNACK,
)


@dataclass(frozen=True, slots=True)
class MacroTargets:
    """Canonical macro-target aggregate used by domain invariant validation."""

    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Canonical user profile input used by energy/macro domain services."""

    age: int
    gender: Gender
    height_cm: int
    weight_kg: float
    activity_level: ActivityLevel


@dataclass(frozen=True, slots=True)
class MealAllocation:
    """Canonical per-meal macro allocation used for domain invariant validation."""

    meal: MealName
    carbs_g: float
    protein_g: float
    fat_g: float
