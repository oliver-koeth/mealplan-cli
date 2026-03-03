"""Tests for composed Phase 4 domain service entrypoints."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

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


def test_calculate_training_carbs_g_returns_zero_for_all_zone_1_minutes() -> None:
    zones_minutes: Mapping[int, int] = {1: 45, 2: 0, 3: 0, 4: 0, 5: 0}

    assert calculate_training_carbs_g(zones_minutes) == 0.0


def test_calculate_training_carbs_g_returns_zero_for_zero_total_minutes() -> None:
    zones_minutes: Mapping[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    assert calculate_training_carbs_g(zones_minutes) == 0.0


@pytest.mark.parametrize(
    ("zones_minutes", "expected_training_carbs_g"),
    [
        ({1: 40, 2: 5, 3: 0, 4: 0, 5: 0}, 45.0),
        ({1: 30, 2: 0, 3: 0, 4: 20, 5: 0}, 50.0),
    ],
    ids=[
        "precedence_any_zone_2_minutes_overrides_all_zone_1_zero_path",
        "precedence_any_zone_4_minutes_overrides_all_zone_1_zero_path",
    ],
)
def test_calculate_training_carbs_g_precedence_mixed_zone_1_with_zone_2_to_5_uses_override_total(
    zones_minutes: Mapping[int, int],
    expected_training_carbs_g: float,
) -> None:
    assert calculate_training_carbs_g(zones_minutes) == expected_training_carbs_g


@pytest.mark.parametrize(
    ("zones_minutes", "expected_training_carbs_g"),
    [
        ({1: 1, 2: 0, 3: 0, 4: 0, 5: 0}, 0.0),
        ({1: 120, 2: 0, 3: 0, 4: 0, 5: 0}, 0.0),
    ],
    ids=[
        "precedence_only_zone_1_short_session_keeps_zero_path",
        "precedence_only_zone_1_long_session_keeps_zero_path",
    ],
)
def test_calculate_training_carbs_g_precedence_boundary_only_zone_1_keeps_zero_path(
    zones_minutes: Mapping[int, int],
    expected_training_carbs_g: float,
) -> None:
    assert calculate_training_carbs_g(zones_minutes) == expected_training_carbs_g


@pytest.mark.parametrize(
    ("zones_minutes", "expected_training_carbs_g"),
    [
        ({1: 10, 2: 20, 3: 0, 4: 0, 5: 0}, 30.0),
        ({1: 15, 2: 0, 3: 45, 4: 0, 5: 0}, 60.0),
        ({1: 0, 2: 0, 3: 0, 4: 30, 5: 0}, 30.0),
        ({1: 25, 2: 0, 3: 0, 4: 0, 5: 70}, 95.0),
    ],
)
def test_calculate_training_carbs_g_uses_total_minutes_when_any_zone_2_to_5_present(
    zones_minutes: Mapping[int, int],
    expected_training_carbs_g: float,
) -> None:
    assert calculate_training_carbs_g(zones_minutes) == expected_training_carbs_g
