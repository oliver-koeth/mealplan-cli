"""Tests for canonical macro-target helpers."""

from __future__ import annotations

import pytest

from mealplan.domain.enums import CarbMode
from mealplan.domain.macros import CARBS_FACTOR_BY_MODE, carbs_target_g_for, protein_target_g_for


def test_protein_target_g_for_uses_canonical_bodyweight_formula() -> None:
    assert protein_target_g_for(72.5) == 145.0


@pytest.mark.parametrize(
    ("carb_mode", "expected_carbs_g"),
    [
        (CarbMode.LOW, 217.5),
        (CarbMode.NORMAL, 362.5),
        (CarbMode.PERIODIZED, 290.0),
    ],
)
def test_carbs_target_g_for_uses_mode_specific_formulas(
    carb_mode: CarbMode,
    expected_carbs_g: float,
) -> None:
    assert carbs_target_g_for(weight_kg=72.5, carb_mode=carb_mode) == expected_carbs_g


def test_carbs_factor_mapping_uses_carb_mode_enum_keys() -> None:
    assert set(CARBS_FACTOR_BY_MODE.keys()) == set(CarbMode)
