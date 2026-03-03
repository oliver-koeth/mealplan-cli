"""Domain layer for mealplan."""

from mealplan.domain.energy import (
    ACTIVITY_FACTOR_BY_LEVEL,
    activity_factor_for,
    bmr_kcal_per_day_for,
    tdee_kcal_per_day_for,
)
from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)
from mealplan.domain.macros import (
    CARBS_FACTOR_BY_MODE,
    carbs_target_g_for,
    fat_target_g_for,
    protein_target_g_for,
)
from mealplan.domain.model import (
    CANONICAL_MEAL_ORDER,
    MacroTargets,
    MealAllocation,
    UserProfile,
)
from mealplan.domain.services import (
    calculate_macro_targets,
    calculate_meal_split_and_response_payload,
    calculate_periodized_carb_allocation,
    calculate_tdee_kcal,
    calculate_training_carbs_g,
)
from mealplan.domain.validation import (
    validate_carb_reconciliation_invariants,
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)

__all__ = [
    "ActivityLevel",
    "ACTIVITY_FACTOR_BY_LEVEL",
    "CARBS_FACTOR_BY_MODE",
    "CANONICAL_MEAL_ORDER",
    "CarbMode",
    "Gender",
    "MacroTargets",
    "MealAllocation",
    "MealName",
    "TrainingLoadTomorrow",
    "UserProfile",
    "activity_factor_for",
    "bmr_kcal_per_day_for",
    "calculate_meal_split_and_response_payload",
    "calculate_macro_targets",
    "calculate_periodized_carb_allocation",
    "calculate_tdee_kcal",
    "calculate_training_carbs_g",
    "carbs_target_g_for",
    "fat_target_g_for",
    "protein_target_g_for",
    "tdee_kcal_per_day_for",
    "validate_carb_reconciliation_invariants",
    "validate_meal_allocation_invariants",
    "validate_macro_targets_invariants",
]
