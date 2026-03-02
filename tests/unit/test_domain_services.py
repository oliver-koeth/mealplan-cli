"""Tests for composed Phase 4 domain service entrypoints."""

from __future__ import annotations

from mealplan.domain.enums import ActivityLevel, CarbMode, Gender
from mealplan.domain.model import MacroTargets, UserProfile
from mealplan.domain.services import calculate_macro_targets, calculate_tdee_kcal


def test_calculate_tdee_kcal_returns_energy_from_typed_profile() -> None:
    profile = UserProfile(
        age=30,
        gender=Gender.MALE,
        height_cm=175,
        weight_kg=70.5,
        activity_level=ActivityLevel.MEDIUM,
    )

    assert calculate_tdee_kcal(profile) == 2273.90625


def test_calculate_macro_targets_returns_macro_targets_dataclass() -> None:
    profile = UserProfile(
        age=30,
        gender=Gender.MALE,
        height_cm=175,
        weight_kg=70.5,
        activity_level=ActivityLevel.MEDIUM,
    )

    macro_targets = calculate_macro_targets(
        profile=profile,
        carb_mode=CarbMode.NORMAL,
        tdee_kcal=calculate_tdee_kcal(profile),
    )

    assert isinstance(macro_targets, MacroTargets)
    assert macro_targets == MacroTargets(
        protein_g=141.0,
        carbs_g=352.5,
        fat_g=33.322916666666664,
    )
