"""Domain energy helpers and canonical activity multipliers."""

from __future__ import annotations

from mealplan.domain.enums import ActivityLevel, Gender
from mealplan.domain.model import UserProfile

ACTIVITY_FACTOR_BY_LEVEL: dict[ActivityLevel, float] = {
    ActivityLevel.LOW: 1.2,
    ActivityLevel.MEDIUM: 1.375,
    ActivityLevel.HIGH: 1.55,
}


def activity_factor_for(activity_level: ActivityLevel) -> float:
    """Return the canonical activity multiplier for TDEE calculations."""
    return ACTIVITY_FACTOR_BY_LEVEL[activity_level]


def bmr_kcal_per_day_for(
    *,
    gender: Gender,
    weight_kg: float,
    height_cm: int,
    age: int,
) -> float:
    """Return BMR in kcal/day using canonical Mifflin-St Jeor equations."""
    base_value = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender is Gender.MALE:
        return base_value + 5
    return base_value - 161


def tdee_kcal_per_day_for(profile: UserProfile) -> float:
    """Return TDEE in kcal/day from a typed user profile."""
    return bmr_kcal_per_day_for(
        gender=profile.gender,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        age=profile.age,
    ) * activity_factor_for(profile.activity_level)
