"""Domain layer for mealplan."""

from mealplan.domain.energy import ACTIVITY_FACTOR_BY_LEVEL, activity_factor_for
from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation
from mealplan.domain.validation import (
    validate_carb_reconciliation_invariants,
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)

__all__ = [
    "ActivityLevel",
    "ACTIVITY_FACTOR_BY_LEVEL",
    "CANONICAL_MEAL_ORDER",
    "CarbMode",
    "Gender",
    "MacroTargets",
    "MealAllocation",
    "MealName",
    "TrainingLoadTomorrow",
    "activity_factor_for",
    "validate_carb_reconciliation_invariants",
    "validate_meal_allocation_invariants",
    "validate_macro_targets_invariants",
]
