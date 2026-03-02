"""Domain macro-target helpers for protein and carbohydrates."""

from __future__ import annotations

from mealplan.domain.enums import CarbMode

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
