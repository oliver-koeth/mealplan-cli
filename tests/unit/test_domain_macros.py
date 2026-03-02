"""Tests for canonical macro-target helpers."""

from __future__ import annotations

import pytest

from mealplan.domain.enums import CarbMode
from mealplan.domain.macros import (
    CARBS_FACTOR_BY_MODE,
    carbs_target_g_for,
    fat_target_g_for,
    protein_target_g_for,
)
from mealplan.shared.errors import DomainRuleError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


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


@pytest.mark.parametrize(
    ("tdee_kcal", "protein_g", "carbs_g", "expected_fat_g"),
    [
        (2500.0, 150.0, 275.0, 88.88888888888889),
        (2200.0, 140.0, 250.0, 71.11111111111111),
    ],
)
def test_fat_target_g_for_residual_formula_matrix(
    tdee_kcal: float,
    protein_g: float,
    carbs_g: float,
    expected_fat_g: float,
) -> None:
    assert (
        fat_target_g_for(tdee_kcal=tdee_kcal, protein_g=protein_g, carbs_g=carbs_g)
        == expected_fat_g
    )


def test_fat_target_g_for_rejects_negative_residual_fat() -> None:
    with pytest.raises(DomainRuleError) as error_info:
        fat_target_g_for(tdee_kcal=1600.0, protein_g=200.0, carbs_g=220.0)

    assert str(error_info.value).startswith("macro_targets.fat_g:")
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN
