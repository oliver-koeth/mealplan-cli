"""Tests for canonical energy-domain activity multipliers."""

from __future__ import annotations

import pytest

from mealplan.domain.energy import ACTIVITY_FACTOR_BY_LEVEL, activity_factor_for
from mealplan.domain.enums import ActivityLevel


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
