"""Tests for composed Phase 4 domain service entrypoints."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import cast

import pytest

from mealplan.application.contracts import MealPlanResponse
from mealplan.domain import (
    calculate_normal_meal_calorie_pool_kcal,
    calculate_training_calorie_demand_kcal,
    calculate_training_carbs_g,
)
from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    CarbStrategy,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, UserProfile
from mealplan.domain.services import (
    CARB_RECONCILIATION_TOLERANCE,
    MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE,
    _assemble_meal_split_response_payload,
    _validate_carb_reconciliation,
    calculate_macro_targets,
    calculate_meal_split_and_response_payload,
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


def test_calculate_training_calorie_demand_kcal_counts_all_zone_minutes() -> None:
    zones_minutes: Mapping[int, int] = {1: 30, 2: 0, 3: 0, 4: 0, 5: 0}

    assert calculate_training_calorie_demand_kcal(zones_minutes) == 120.0


def test_calculate_normal_meal_calorie_pool_kcal_subtracts_training_supply_from_day_energy(
) -> None:
    assert (
        calculate_normal_meal_calorie_pool_kcal(
            tdee_kcal=2310.0,
            training_calorie_demand_kcal=320.0,
            training_carbs_g=80.0,
        )
        == 2310.0
    )


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


def test_calculate_meal_split_and_response_payload_has_stable_orchestration_signature() -> None:
    signature = inspect.signature(calculate_meal_split_and_response_payload)

    assert str(signature) == (
        "(tdee_kcal: 'float', training_carbs_g: 'float', training_calorie_demand_kcal: 'float', "
        "carb_mode: 'CarbMode', "
        "training_before_meal: 'MealName | None', "
        "training_load_tomorrow: 'TrainingLoadTomorrow', "
        "protein_g: 'float', carbs_g: 'float', fat_g: 'float', "
        "carb_allocation_g_by_meal: 'Mapping[MealName, float]') -> 'dict[str, object]'"
    )


def test_calculate_meal_split_and_response_payload_inserts_training_meal_before_target() -> None:
    carb_allocation_g_by_meal = dict(
        zip(
            CANONICAL_MEAL_ORDER,
            [70.0, 30.0, 90.0, 40.0, 60.0, 10.0],
            strict=True,
        )
    )

    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2908.0,
        training_carbs_g=85.0,
        training_calorie_demand_kcal=340.0,
        carb_mode=CarbMode.NORMAL,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=carb_allocation_g_by_meal,
    )

    assert list(payload.keys()) == [
        "TDEE",
        "training_carbs_g",
        "protein_g",
        "carbs_g",
        "fat_g",
        "total_kcal",
        "meals",
    ]
    assert payload["TDEE"] == 2908.0
    assert payload["training_carbs_g"] == 85.0
    assert payload["protein_g"] == 180.0
    assert payload["carbs_g"] == 300.0
    assert payload["fat_g"] == 72.0
    assert payload["total_kcal"] == 3248.0

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert len(meals) == len(CANONICAL_MEAL_ORDER) + 1
    meal_sequence = [entry["meal"] for entry in meals]
    assert meal_sequence == [
        MealName.BREAKFAST,
        MealName.MORNING_SNACK,
        "training",
        MealName.LUNCH,
        MealName.AFTERNOON_SNACK,
        MealName.DINNER,
        MealName.EVENING_SNACK,
    ]
    assert meals[2] == {
        "meal": "training",
        "carbs_strategy": CarbStrategy.HIGH,
        "carbs_g": 85.0,
        "protein_g": 0.0,
        "fat_g": 0.0,
        "kcal": 340.0,
    }
    canonical_meals = [entry for entry in meals if entry["meal"] != "training"]
    assert [entry["carbs_strategy"] for entry in canonical_meals] == [CarbStrategy.MEDIUM] * 6
    assert [entry["carbs_g"] for entry in canonical_meals] == [70.0, 30.0, 90.0, 40.0, 60.0, 10.0]
    assert [entry["protein_g"] for entry in canonical_meals] == [40.0, 20.0, 40.0, 20.0, 40.0, 20.0]
    assert round(sum(float(entry["kcal"]) for entry in canonical_meals), 2) == 2908.0
    assert payload["total_kcal"] == pytest.approx(
        2908.0 + calculate_training_calorie_demand_kcal({1: 0, 2: 85, 3: 0, 4: 0, 5: 0}),
    )
    assert [entry["fat_g"] for entry in canonical_meals] == [12.0] * len(CANONICAL_MEAL_ORDER)
    assert [entry["kcal"] for entry in canonical_meals] == [
        646.22,
        323.11,
        646.22,
        323.11,
        646.22,
        323.12,
    ]


@pytest.mark.parametrize("training_before_meal", list(CANONICAL_MEAL_ORDER))
def test_calculate_meal_split_and_response_payload_deterministically_inserts_before_each_target(
    training_before_meal: MealName,
) -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=60.0,
        training_calorie_demand_kcal=240.0,
        carb_mode=CarbMode.LOW,
        training_before_meal=training_before_meal,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["meal"] for entry in meals].count("training") == 1
    training_idx = next(
        idx for idx, meal in enumerate(meals) if meal["meal"] == "training"
    )
    assert meals[training_idx + 1]["meal"] == training_before_meal
    assert [entry["meal"] for entry in meals if entry["meal"] != "training"] == list(
        CANONICAL_MEAL_ORDER
    )


def test_assemble_meal_split_response_payload_includes_top_level_fields_and_meals() -> None:
    meals = [
        {
            "meal": meal,
            "carbs_strategy": CarbStrategy.LOW,
            "carbs_g": 10.0,
            "protein_g": 20.0,
            "fat_g": 5.0,
            "kcal": 165.0,
        }
        for meal in CANONICAL_MEAL_ORDER
    ]

    payload = _assemble_meal_split_response_payload(
        tdee_kcal=2300.0,
        training_carbs_g=55.0,
        protein_g=120.0,
        carbs_g=200.0,
        fat_g=60.0,
        total_kcal=990.0,
        meals=meals,
    )

    assert list(payload.keys()) == [
        "TDEE",
        "training_carbs_g",
        "protein_g",
        "carbs_g",
        "fat_g",
        "total_kcal",
        "meals",
    ]
    assert payload["TDEE"] == 2300.0
    assert payload["training_carbs_g"] == 55.0
    assert payload["protein_g"] == 120.0
    assert payload["carbs_g"] == 200.0
    assert payload["fat_g"] == 60.0
    assert payload["total_kcal"] == 990.0
    assert payload["meals"] == meals


def test_calculate_meal_split_payload_is_meal_plan_response_compatible_shape() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=85.0,
        training_calorie_demand_kcal=340.0,
        carb_mode=CarbMode.LOW,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    parsed = MealPlanResponse.model_validate(payload)

    assert parsed.TDEE == 2400.0
    assert parsed.training_carbs_g == 85.0
    assert parsed.protein_g == 180.0
    assert parsed.carbs_g == 300.0
    assert parsed.fat_g == 72.0
    assert len(parsed.meals) == len(CANONICAL_MEAL_ORDER) + 1
    training_meal = next(meal for meal in parsed.meals if meal.meal == "training")
    assert training_meal.carbs_strategy == CarbStrategy.HIGH
    assert training_meal.carbs_g == 85.0
    assert training_meal.protein_g == 0.0
    assert training_meal.fat_g == 0.0
    assert training_meal.kcal == 340.0


def test_calculate_meal_split_and_response_payload_uses_canonical_protein_and_kcal_shares() -> None:
    protein_g = 145.0
    fat_g = 73.0
    expected_per_meal_fat_g = round(fat_g / float(len(CANONICAL_MEAL_ORDER)), 2)
    expected_protein_g = [32.22, 16.11, 32.22, 16.11, 32.22, 16.12]
    expected_kcal = [541.56, 270.78, 541.56, 270.78, 541.56, 270.76]

    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2437.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.LOW,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=protein_g,
        carbs_g=300.0,
        fat_g=fat_g,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["carbs_strategy"] for entry in meals] == [CarbStrategy.LOW] * 6
    assert [entry["protein_g"] for entry in meals] == expected_protein_g
    assert [entry["fat_g"] for entry in meals[:-1]] == [expected_per_meal_fat_g] * 5
    assert meals[-1]["fat_g"] == 12.15
    assert [entry["kcal"] for entry in meals] == expected_kcal
    assert sum(float(entry["protein_g"]) for entry in meals) == pytest.approx(protein_g)
    assert sum(float(entry["fat_g"]) for entry in meals) == pytest.approx(fat_g)


def test_meal_split_rounds_meal_macro_fields_to_two_decimals_at_boundary() -> None:
    protein_g = 100.0
    fat_g = 50.0
    expected_per_meal_fat_g = fat_g / float(len(CANONICAL_MEAL_ORDER))
    carb_allocation_g_by_meal = dict(
        zip(
            CANONICAL_MEAL_ORDER,
            [20.001, 30.004, 40.005, 50.006, 60.444, 39.54],
            strict=True,
        )
    )

    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2100.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.NORMAL,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=protein_g,
        carbs_g=240.0,
        fat_g=fat_g,
        carb_allocation_g_by_meal=carb_allocation_g_by_meal,
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["carbs_strategy"] for entry in meals] == [CarbStrategy.MEDIUM] * 6
    assert [entry["protein_g"] for entry in meals] == [22.22, 11.11, 22.22, 11.11, 22.22, 11.12]
    assert [entry["fat_g"] for entry in meals[:-1]] == [round(expected_per_meal_fat_g, 2)] * 5
    assert meals[-1]["fat_g"] == 8.35
    assert [entry["carbs_g"] for entry in meals] == [20.0, 30.0, 40.01, 50.01, 60.44, 39.54]
    assert payload["protein_g"] == protein_g
    assert payload["carbs_g"] == 240.0
    assert payload["fat_g"] == fat_g


def test_meal_split_applies_residual_adjustment_to_evening_snack_only() -> None:
    carb_allocation_g_by_meal = dict.fromkeys(CANONICAL_MEAL_ORDER, 10.005)

    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2200.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=100.0,
        carbs_g=60.03,
        fat_g=10.0,
        carb_allocation_g_by_meal=carb_allocation_g_by_meal,
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["carbs_strategy"] for entry in meals] == [CarbStrategy.LOW] * 6

    assert [entry["carbs_g"] for entry in meals[:-1]] == [10.01, 10.01, 10.01, 10.01, 10.01]
    assert [entry["protein_g"] for entry in meals[:-1]] == [22.22, 11.11, 22.22, 11.11, 22.22]
    assert [entry["fat_g"] for entry in meals[:-1]] == [1.67, 1.67, 1.67, 1.67, 1.67]

    evening_snack = meals[-1]
    assert evening_snack["meal"] == MealName.EVENING_SNACK
    assert evening_snack["carbs_g"] == 9.98
    assert evening_snack["protein_g"] == 11.12
    assert evening_snack["fat_g"] == 1.65

    assert sum(float(entry["carbs_g"]) for entry in meals) == pytest.approx(payload["carbs_g"])
    assert sum(float(entry["protein_g"]) for entry in meals) == pytest.approx(payload["protein_g"])
    assert sum(float(entry["fat_g"]) for entry in meals) == pytest.approx(payload["fat_g"])


def test_meal_split_keeps_evening_snack_unchanged_when_rounded_sums_match_targets() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2200.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.NORMAL,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=120.0,
        carbs_g=60.0,
        fat_g=30.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 10.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert meals[-1]["meal"] == MealName.EVENING_SNACK
    assert [entry["carbs_strategy"] for entry in meals] == [CarbStrategy.MEDIUM] * 6
    assert meals[-1]["carbs_g"] == 10.0
    assert meals[-1]["protein_g"] == 13.33
    assert meals[-1]["fat_g"] == 5.0
    assert sum(float(entry["carbs_g"]) for entry in meals) == pytest.approx(payload["carbs_g"])
    assert sum(float(entry["protein_g"]) for entry in meals) == pytest.approx(payload["protein_g"])
    assert sum(float(entry["fat_g"]) for entry in meals) == pytest.approx(payload["fat_g"])


def test_meal_split_reconciles_displayed_kcal_sum_to_tdee_on_evening_snack_only() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=990.03,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.NORMAL,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=120.0,
        carbs_g=60.0,
        fat_g=30.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 10.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["kcal"] for entry in meals[:-1]] == [220.01, 110.0, 220.01, 110.0, 220.01]
    assert meals[-1]["meal"] == MealName.EVENING_SNACK
    assert [entry["carbs_strategy"] for entry in meals] == [CarbStrategy.MEDIUM] * 6
    assert meals[-1]["carbs_g"] == 10.0
    assert meals[-1]["protein_g"] == 13.33
    assert meals[-1]["fat_g"] == 5.0
    assert meals[-1]["kcal"] == 110.0
    assert sum(float(entry["kcal"]) for entry in meals) == pytest.approx(payload["TDEE"])


def test_meal_split_kcal_reconciliation_is_display_only_with_training_meal() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=1230.03,
        training_carbs_g=60.0,
        training_calorie_demand_kcal=240.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=120.0,
        carbs_g=60.0,
        fat_g=30.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 10.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["meal"] for entry in meals].count("training") == 1

    training_meal = next(entry for entry in meals if entry["meal"] == "training")
    assert training_meal["carbs_strategy"] == CarbStrategy.HIGH
    assert training_meal["carbs_g"] == 60.0
    assert training_meal["protein_g"] == 0.0
    assert training_meal["fat_g"] == 0.0
    assert training_meal["kcal"] == 240.0

    evening_snack = next(entry for entry in meals if entry["meal"] == MealName.EVENING_SNACK)
    assert [entry["carbs_strategy"] for entry in meals if entry["meal"] != "training"] == [
        CarbStrategy.LOW,
        CarbStrategy.LOW,
        CarbStrategy.HIGH,
        CarbStrategy.HIGH,
        CarbStrategy.LOW,
        CarbStrategy.LOW,
    ]
    assert evening_snack["carbs_g"] == 10.0
    assert evening_snack["protein_g"] == 13.33
    assert evening_snack["fat_g"] == 5.0
    assert evening_snack["kcal"] == 136.67

    assert [entry["kcal"] for entry in meals if entry["meal"] != "training"] == [
        273.34,
        136.67,
        273.34,
        136.67,
        273.34,
        136.67,
    ]
    assert sum(float(entry["kcal"]) for entry in meals) == pytest.approx(
        payload["TDEE"] + 240.0
    )


def test_meal_split_allows_subcent_target_delta_within_reconciliation_tolerance() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2200.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.LOW,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=100.0,
        carbs_g=60.035,
        fat_g=10.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 10.005),
    )

    meals = payload["meals"]
    reconciled_carbs = sum(float(entry["carbs_g"]) for entry in meals)
    assert abs(reconciled_carbs - payload["carbs_g"]) <= MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE


def test_calculate_meal_split_and_response_payload_omits_training_meal_when_zero() -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.LOW,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["meal"] for entry in meals] == list(CANONICAL_MEAL_ORDER)


def test_meal_split_raises_for_missing_carb_allocation_meals() -> None:
    incomplete_carb_allocation = dict(
        zip(
            CANONICAL_MEAL_ORDER[:-1],
            [50.0, 50.0, 50.0, 50.0, 50.0],
            strict=True,
        )
    )

    with pytest.raises(DomainRuleError, match=r"^meal_assembly\.carb_allocation:"):
        calculate_meal_split_and_response_payload(
            tdee_kcal=2400.0,
            training_carbs_g=70.0,
            training_calorie_demand_kcal=280.0,
            carb_mode=CarbMode.NORMAL,
            training_before_meal=MealName.LUNCH,
            training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
            protein_g=180.0,
            carbs_g=300.0,
            fat_g=70.0,
            carb_allocation_g_by_meal=incomplete_carb_allocation,
        )


def test_meal_split_raises_for_extra_carb_allocation_meals() -> None:
    carb_allocation_with_extra_key = cast(
        Mapping[MealName, float],
        {
            **dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
            "late-night": 0.0,
        },
    )

    with pytest.raises(DomainRuleError, match=r"^meal_assembly\.carb_allocation:"):
        calculate_meal_split_and_response_payload(
            tdee_kcal=2400.0,
            training_carbs_g=70.0,
            training_calorie_demand_kcal=280.0,
            carb_mode=CarbMode.NORMAL,
            training_before_meal=MealName.LUNCH,
            training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
            protein_g=180.0,
            carbs_g=300.0,
            fat_g=70.0,
            carb_allocation_g_by_meal=carb_allocation_with_extra_key,
        )


@pytest.mark.parametrize(
    ("carb_mode", "expected_strategy"),
    [
        (CarbMode.NORMAL, CarbStrategy.MEDIUM),
        (CarbMode.LOW, CarbStrategy.LOW),
        (CarbMode.PERIODIZED, CarbStrategy.LOW),
    ],
)
def test_calculate_meal_split_and_response_payload_assigns_baseline_carb_strategy_by_mode(
    carb_mode: CarbMode,
    expected_strategy: CarbStrategy,
) -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=carb_mode,
        training_before_meal=None,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = payload["meals"]
    assert isinstance(meals, list)
    assert [entry["carbs_strategy"] for entry in meals] == [expected_strategy] * 6


def test_calculate_meal_split_and_response_payload_marks_two_post_training_periodized_meals_high(
) -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = cast(list[dict[str, object]], payload["meals"])
    assert [entry["carbs_strategy"] for entry in meals] == [
        CarbStrategy.LOW,
        CarbStrategy.LOW,
        CarbStrategy.HIGH,
        CarbStrategy.HIGH,
        CarbStrategy.LOW,
        CarbStrategy.LOW,
    ]


@pytest.mark.parametrize(
    ("training_before_meal", "expected_high_meals"),
    [
        (MealName.DINNER, {MealName.DINNER}),
        (MealName.EVENING_SNACK, {MealName.EVENING_SNACK}),
    ],
)
def test_calculate_meal_split_and_response_payload_periodized_does_not_wrap_high_strategy(
    training_before_meal: MealName,
    expected_high_meals: set[MealName],
) -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=training_before_meal,
        training_load_tomorrow=TrainingLoadTomorrow.MEDIUM,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = cast(list[dict[str, object]], payload["meals"])
    high_meals = {
        cast(MealName, entry["meal"])
        for entry in meals
        if entry["carbs_strategy"] is CarbStrategy.HIGH
    }
    assert high_meals == expected_high_meals


@pytest.mark.parametrize(
    ("training_before_meal", "expected_high_meals"),
    [
        (MealName.DINNER, {MealName.DINNER}),
        (MealName.EVENING_SNACK, {MealName.DINNER, MealName.EVENING_SNACK}),
    ],
)
def test_calculate_meal_split_and_response_payload_periodized_tomorrow_high_forces_dinner(
    training_before_meal: MealName,
    expected_high_meals: set[MealName],
) -> None:
    payload = calculate_meal_split_and_response_payload(
        tdee_kcal=2400.0,
        training_carbs_g=0.0,
        training_calorie_demand_kcal=0.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=training_before_meal,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
        protein_g=180.0,
        carbs_g=300.0,
        fat_g=72.0,
        carb_allocation_g_by_meal=dict.fromkeys(CANONICAL_MEAL_ORDER, 50.0),
    )

    meals = cast(list[dict[str, object]], payload["meals"])
    high_meals = {
        cast(MealName, entry["meal"])
        for entry in meals
        if entry["carbs_strategy"] is CarbStrategy.HIGH
    }
    assert high_meals == expected_high_meals


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
