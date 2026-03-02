"""Domain energy helpers and canonical activity multipliers."""

from __future__ import annotations

from mealplan.domain.enums import ActivityLevel

ACTIVITY_FACTOR_BY_LEVEL: dict[ActivityLevel, float] = {
    ActivityLevel.LOW: 1.2,
    ActivityLevel.MEDIUM: 1.375,
    ActivityLevel.HIGH: 1.55,
}


def activity_factor_for(activity_level: ActivityLevel) -> float:
    """Return the canonical activity multiplier for TDEE calculations."""
    return ACTIVITY_FACTOR_BY_LEVEL[activity_level]
