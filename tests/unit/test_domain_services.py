"""Tests for composed Phase 4 domain service entrypoints."""

from __future__ import annotations

from collections.abc import Mapping

from mealplan.domain import calculate_training_carbs_g
from mealplan.domain.enums import ActivityLevel, CarbMode, Gender
from mealplan.domain.model import MacroTargets, UserProfile
from mealplan.domain.services import (
    calculate_macro_targets,
    calculate_tdee_kcal,
)


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


def test_calculate_training_carbs_g_returns_float_from_normalized_zone_minutes() -> None:
    zones_minutes: Mapping[int, int] = {1: 20, 2: 40, 3: 0, 4: 0, 5: 0}

    training_carbs_g = calculate_training_carbs_g(zones_minutes)

    assert isinstance(training_carbs_g, float)
    assert training_carbs_g == 60.0


def test_calculate_training_carbs_g_is_deterministic_for_same_input() -> None:
    zones_minutes: Mapping[int, int] = {1: 10, 2: 0, 3: 15, 4: 5, 5: 0}

    assert calculate_training_carbs_g(zones_minutes) == calculate_training_carbs_g(zones_minutes)
