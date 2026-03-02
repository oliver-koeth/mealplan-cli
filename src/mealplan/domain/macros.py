"""Domain macro-target helpers for protein and carbohydrates."""

from __future__ import annotations

from mealplan.domain.enums import CarbMode
from mealplan.shared.errors import DomainRuleError

CARBS_FACTOR_BY_MODE: dict[CarbMode, float] = {
    CarbMode.LOW: 3.0,
    CarbMode.NORMAL: 5.0,
    CarbMode.PERIODIZED: 4.0,
}


def protein_target_g_for(weight_kg: float) -> float:
    """Return canonical daily protein target in grams."""
    return 2 * weight_kg


def carbs_target_g_for(*, weight_kg: float, carb_mode: CarbMode) -> float:
    """Return canonical daily carbohydrate target in grams for the selected mode."""
    return CARBS_FACTOR_BY_MODE[carb_mode] * weight_kg


def fat_target_g_for(*, tdee_kcal: float, protein_g: float, carbs_g: float) -> float:
    """Return residual daily fat target in grams."""
    fat_kcal = tdee_kcal - (protein_g * 4) - (carbs_g * 4)
    fat_g = fat_kcal / 9
    if fat_g < 0:
        raise DomainRuleError(
            "macro_targets.fat_g: residual fat target must be greater than or equal to 0"
        )
    return fat_g
