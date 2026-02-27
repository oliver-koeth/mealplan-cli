"""Canonical enum definitions for domain-wide contracts."""

from __future__ import annotations

from enum import StrEnum


class Gender(StrEnum):
    """Supported biological sex labels used by current equations."""

    MALE = "male"
    FEMALE = "female"


class ActivityLevel(StrEnum):
    """Activity multipliers bucket labels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CarbMode(StrEnum):
    """Carbohydrate planning modes."""

    LOW = "low"
    NORMAL = "normal"
    PERIODIZED = "periodized"


class TrainingLoadTomorrow(StrEnum):
    """Expected next-day workload labels for periodization rules."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MealName(StrEnum):
    """Canonical meal identifiers in output contracts."""

    BREAKFAST = "breakfast"
    MORNING_SNACK = "morning-snack"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon-snack"
    DINNER = "dinner"
    EVENING_SNACK = "evening-snack"
