"""Domain layer for mealplan."""

from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation
from mealplan.domain.validation import (
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)

__all__ = [
    "ActivityLevel",
    "CANONICAL_MEAL_ORDER",
    "CarbMode",
    "Gender",
    "MacroTargets",
    "MealAllocation",
    "MealName",
    "TrainingLoadTomorrow",
    "validate_meal_allocation_invariants",
    "validate_macro_targets_invariants",
]
