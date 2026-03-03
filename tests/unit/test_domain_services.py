"""Tests for composed Phase 4 domain service entrypoints."""

from __future__ import annotations

import inspect
from collections.abc import Mapping

import pytest

from mealplan.domain import calculate_training_carbs_g
from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, MealName, TrainingLoadTomorrow
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, UserProfile
from mealplan.domain.services import (
    CARB_RECONCILIATION_TOLERANCE,
    _validate_carb_reconciliation,
    calculate_macro_targets,
    calculate_periodized_carb_allocation,
    calculate_tdee_kcal,
)
from mealplan.domain.services import (
    calculate_training_carbs_g as calculate_training_carbs_g_service,
)
from mealplan.shared.errors import DomainRuleError


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


def test_calculate_training_carbs_g_has_stable_orchestration_signature() -> None:
    signature = inspect.signature(calculate_training_carbs_g_service)

    assert str(signature) == "(zones_minutes: 'Mapping[int, int]') -> 'float'"


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


@pytest.mark.parametrize(
    ("zones_minutes", "expected_training_carbs_g"),
    [
        ({1: 45, 2: 0, 3: 0, 4: 0, 5: 0}, 0.0),
        ({1: 0, 2: 30, 3: 0, 4: 0, 5: 0}, 30.0),
        ({1: 20, 2: 0, 3: 40, 4: 0, 5: 0}, 60.0),
        ({1: 0, 2: 15, 3: 25, 4: 10, 5: 0}, 50.0),
        ({1: 0, 2: 0, 3: 0, 4: 0, 5: 0}, 0.0),
    ],
    ids=[
        "matrix_only_zone_1_active",
        "matrix_only_zone_2_active",
        "matrix_mixed_zone_1_plus_zone_3",
        "matrix_multiple_zone_2_to_5_active",
        "matrix_all_zones_zero",
    ],
)
def test_calculate_training_carbs_g_medium_depth_permutation_matrix(
    zones_minutes: Mapping[int, int],
    expected_training_carbs_g: float,
) -> None:
    assert calculate_training_carbs_g(zones_minutes) == expected_training_carbs_g


def test_calculate_periodized_carb_allocation_has_stable_orchestration_signature() -> None:
    signature = inspect.signature(calculate_periodized_carb_allocation)

    assert str(signature) == (
        "(carb_mode: 'CarbMode', daily_carbs_g: 'float', "
        "training_before_meal: 'MealName | None', "
        "training_load_tomorrow: 'TrainingLoadTomorrow') -> 'dict[MealName, float]'"
    )


def test_calculate_periodized_carb_allocation_marks_two_post_training_meals_high() -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=360.0,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
    )

    assert list(allocation.keys()) == list(CANONICAL_MEAL_ORDER)
    assert allocation == {
        MealName.BREAKFAST: 36.0,
        MealName.MORNING_SNACK: 36.0,
        MealName.LUNCH: 108.0,
        MealName.AFTERNOON_SNACK: 108.0,
        MealName.DINNER: 36.0,
        MealName.EVENING_SNACK: 36.0,
    }


def test_calculate_periodized_carb_allocation_wraps_second_high_meal_to_breakfast() -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=300.0,
        training_before_meal=MealName.EVENING_SNACK,
        training_load_tomorrow=TrainingLoadTomorrow.LOW,
    )

    assert allocation[MealName.EVENING_SNACK] == 90.0
    assert allocation[MealName.BREAKFAST] == 90.0


def test_calculate_periodized_carb_allocation_splits_remaining_carbs_evenly() -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=250.0,
        training_before_meal=MealName.MORNING_SNACK,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
    )

    assert allocation[MealName.MORNING_SNACK] == 75.0
    assert allocation[MealName.LUNCH] == 75.0
    assert allocation[MealName.BREAKFAST] == 25.0
    assert allocation[MealName.AFTERNOON_SNACK] == 25.0
    assert allocation[MealName.DINNER] == 25.0
    assert allocation[MealName.EVENING_SNACK] == 25.0


def test_periodized_carb_allocation_applies_tomorrow_high_override_without_conflict() -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=300.0,
        training_before_meal=MealName.BREAKFAST,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )

    assert allocation == {
        MealName.BREAKFAST: 90.0,
        MealName.MORNING_SNACK: 90.0,
        MealName.LUNCH: 10.0,
        MealName.AFTERNOON_SNACK: 10.0,
        MealName.DINNER: 90.0,
        MealName.EVENING_SNACK: 10.0,
    }


@pytest.mark.parametrize("carb_mode", [CarbMode.LOW, CarbMode.NORMAL])
def test_calculate_periodized_carb_allocation_precedence_non_periodized_bypass_wins(
    carb_mode: CarbMode,
) -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=carb_mode,
        daily_carbs_g=300.0,
        training_before_meal=MealName.BREAKFAST,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )

    assert allocation == dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0)


@pytest.mark.parametrize("carb_mode", [CarbMode.LOW, CarbMode.NORMAL])
def test_calculate_periodized_carb_allocation_non_periodized_bypass_uses_exact_division(
    carb_mode: CarbMode,
) -> None:
    daily_carbs_g = 301.0
    expected_per_meal = daily_carbs_g / 6.0

    allocation = calculate_periodized_carb_allocation(
        carb_mode=carb_mode,
        daily_carbs_g=daily_carbs_g,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )

    assert allocation == dict.fromkeys(CANONICAL_MEAL_ORDER, expected_per_meal)


@pytest.mark.parametrize(
    "training_before_meal",
    [MealName.DINNER, MealName.EVENING_SNACK],
)
def test_calculate_periodized_carb_allocation_skips_tomorrow_high_override_on_conflict(
    training_before_meal: MealName,
) -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=300.0,
        training_before_meal=training_before_meal,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )
    allocation_without_override = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=300.0,
        training_before_meal=training_before_meal,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
    )

    assert allocation == allocation_without_override


def test_calculate_periodized_carb_allocation_precedence_keeps_post_training_highs() -> None:
    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=240.0,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )

    assert allocation[MealName.LUNCH] == 72.0
    assert allocation[MealName.AFTERNOON_SNACK] == 72.0
    assert allocation[MealName.DINNER] == 72.0
    assert allocation[MealName.EVENING_SNACK] == 8.0


@pytest.mark.parametrize("carb_mode", [CarbMode.LOW, CarbMode.NORMAL, CarbMode.PERIODIZED])
def test_calculate_periodized_carb_allocation_is_deterministic_for_identical_inputs(
    carb_mode: CarbMode,
) -> None:
    first = calculate_periodized_carb_allocation(
        carb_mode=carb_mode,
        daily_carbs_g=210.0,
        training_before_meal=MealName.DINNER,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )
    second = calculate_periodized_carb_allocation(
        carb_mode=carb_mode,
        daily_carbs_g=210.0,
        training_before_meal=MealName.DINNER,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
    )

    assert first == second


@pytest.mark.parametrize(
    ("training_before_meal", "training_load_tomorrow"),
    [
        (training_before_meal, training_load_tomorrow)
        for training_before_meal in CANONICAL_MEAL_ORDER
        for training_load_tomorrow in TrainingLoadTomorrow
    ],
    ids=[
        (
            f"matrix_training_before_{training_before_meal.value}_"
            f"load_{training_load_tomorrow.value}"
        )
        for training_before_meal in CANONICAL_MEAL_ORDER
        for training_load_tomorrow in TrainingLoadTomorrow
    ],
)
def test_calculate_periodized_carb_allocation_exhaustive_precedence_conflict_matrix(
    training_before_meal: MealName,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> None:
    daily_carbs_g = 300.0
    high_meal_carbs_g = 0.30 * daily_carbs_g

    allocation = calculate_periodized_carb_allocation(
        carb_mode=CarbMode.PERIODIZED,
        daily_carbs_g=daily_carbs_g,
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
    )

    post_training_start_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
    post_training_high_meals = {
        CANONICAL_MEAL_ORDER[post_training_start_idx],
        CANONICAL_MEAL_ORDER[(post_training_start_idx + 1) % len(CANONICAL_MEAL_ORDER)],
    }
    conflict_with_tomorrow_override = training_before_meal in {
        MealName.DINNER,
        MealName.EVENING_SNACK,
    }

    if (
        training_load_tomorrow is TrainingLoadTomorrow.HIGH
        and not conflict_with_tomorrow_override
    ):
        expected_high_meals = (post_training_high_meals | {MealName.DINNER}) - {
            MealName.EVENING_SNACK
        }
    else:
        expected_high_meals = post_training_high_meals

    actual_high_meals = {
        meal for meal, carbs_g in allocation.items() if carbs_g == high_meal_carbs_g
    }
    assert actual_high_meals == expected_high_meals

    expected_low_meal_carbs_g = (
        daily_carbs_g - (float(len(expected_high_meals)) * high_meal_carbs_g)
    ) / float(len(CANONICAL_MEAL_ORDER) - len(expected_high_meals))
    for meal in CANONICAL_MEAL_ORDER:
        expected_carbs_g = (
            high_meal_carbs_g if meal in expected_high_meals else expected_low_meal_carbs_g
        )
        assert allocation[meal] == pytest.approx(expected_carbs_g)

    assert sum(allocation.values()) == pytest.approx(
        daily_carbs_g,
        abs=CARB_RECONCILIATION_TOLERANCE,
    )


def test_validate_carb_reconciliation_allows_delta_within_tolerance() -> None:
    allocation = dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0)

    _validate_carb_reconciliation(
        allocation=allocation,
        daily_carbs_g=300.0 - CARB_RECONCILIATION_TOLERANCE,
    )


def test_validate_carb_reconciliation_raises_domain_rule_error_above_tolerance() -> None:
    allocation = dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0)
    daily_carbs_g = 300.0 - (CARB_RECONCILIATION_TOLERANCE * 1.01)

    with pytest.raises(DomainRuleError, match=r"^carb_reconciliation:"):
        _validate_carb_reconciliation(
            allocation=allocation,
            daily_carbs_g=daily_carbs_g,
        )
