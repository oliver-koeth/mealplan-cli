"""Tests for canonical energy-domain activity multipliers."""

from __future__ import annotations

import pytest

from mealplan.domain.energy import (
    ACTIVITY_FACTOR_BY_LEVEL,
    activity_factor_for,
    bmr_kcal_per_day_for,
    tdee_kcal_per_day_for,
)
from mealplan.domain.enums import ActivityLevel, Gender
from mealplan.domain.model import UserProfile


@pytest.mark.parametrize(
    ("activity_level", "expected_factor"),
    [
        (ActivityLevel.LOW, 1.2),
        (ActivityLevel.MEDIUM, 1.375),
        (ActivityLevel.HIGH, 1.55),
    ],
)
def test_activity_factor_for_returns_canonical_multiplier(
    activity_level: ActivityLevel,
    expected_factor: float,
) -> None:
    assert activity_factor_for(activity_level) == expected_factor


def test_activity_factor_mapping_uses_activity_level_enum_keys() -> None:
    assert set(ACTIVITY_FACTOR_BY_LEVEL.keys()) == set(ActivityLevel)


@pytest.mark.parametrize(
    ("gender", "weight_kg", "height_cm", "age", "expected_bmr"),
    [
        (Gender.MALE, 70.5, 175, 30, 1653.75),
        (Gender.FEMALE, 70.5, 175, 30, 1487.75),
        (Gender.MALE, 60.0, 165, 40, 1436.25),
        (Gender.FEMALE, 60.0, 165, 40, 1270.25),
    ],
)
def test_bmr_kcal_per_day_for_formula_matrix(
    gender: Gender,
    weight_kg: float,
    height_cm: int,
    age: int,
    expected_bmr: float,
) -> None:
    assert (
        bmr_kcal_per_day_for(
            gender=gender,
            weight_kg=weight_kg,
            height_cm=height_cm,
            age=age,
        )
        == expected_bmr
    )


@pytest.mark.parametrize(
    ("gender", "activity_level", "expected_tdee"),
    [
        (Gender.MALE, ActivityLevel.LOW, 1984.5),
        (Gender.MALE, ActivityLevel.MEDIUM, 2273.90625),
        (Gender.MALE, ActivityLevel.HIGH, 2563.3125),
        (Gender.FEMALE, ActivityLevel.LOW, 1785.3),
        (Gender.FEMALE, ActivityLevel.MEDIUM, 2045.65625),
        (Gender.FEMALE, ActivityLevel.HIGH, 2306.0125),
    ],
)
def test_tdee_kcal_per_day_for_formula_matrix(
    gender: Gender,
    activity_level: ActivityLevel,
    expected_tdee: float,
) -> None:
    profile = UserProfile(
        age=30,
        gender=gender,
        height_cm=175,
        weight_kg=70.5,
        activity_level=activity_level,
    )

    assert tdee_kcal_per_day_for(profile) == pytest.approx(expected_tdee)
