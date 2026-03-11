"""Composed domain service entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict, cast

from mealplan.domain.energy import tdee_kcal_per_day_for
from mealplan.domain.enums import CarbMode, CarbStrategy, Gender, MealName, TrainingLoadTomorrow
from mealplan.domain.macros import carbs_target_g_for, fat_target_g_for, protein_target_g_for
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, MealAllocation, UserProfile
from mealplan.domain.validation import validate_meal_allocation_invariants
from mealplan.shared.errors import DomainRuleError

CARB_RECONCILIATION_TOLERANCE = 1e-9
MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE = 1e-2
MacroField = Literal["carbs_g", "protein_g", "fat_g"]
MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER: tuple[MacroField, MacroField, MacroField] = (
    "carbs_g",
    "protein_g",
    "fat_g",
)
CANONICAL_MEAL_SHARE_UNITS: tuple[int, int, int, int, int, int] = (2, 1, 2, 1, 2, 1)
CANONICAL_MEAL_SHARE_TOTAL = sum(CANONICAL_MEAL_SHARE_UNITS)
CARB_CALORIE_SHARE_BY_STRATEGY: dict[CarbStrategy, float] = {
    CarbStrategy.LOW: 0.25,
    CarbStrategy.MEDIUM: 2.0 / 3.0,
    CarbStrategy.HIGH: 0.75,
}
ZONE_INTENSITY_BY_ZONE: dict[int, float] = {
    1: 0.30,
    2: 0.50,
    3: 0.65,
    4: 0.80,
    5: 0.925,
}


class MealPayloadRow(TypedDict):
    meal: MealName | Literal["training"]
    carbs_strategy: CarbStrategy
    carbs_g: float
    protein_g: float
    fat_g: float
    kcal: float


class MealAssemblyResult(TypedDict):
    payload: dict[str, object]
    warnings: tuple[str, ...]


def calculate_tdee_kcal(profile: UserProfile) -> float:
    """Return canonical daily energy expenditure for a typed user profile."""
    return tdee_kcal_per_day_for(profile)


def calculate_macro_targets(
    *,
    profile: UserProfile,
    carb_mode: CarbMode,
    tdee_kcal: float,
) -> MacroTargets:
    """Return canonical macro targets derived from profile, mode, and TDEE."""
    protein_g = protein_target_g_for(profile.weight_kg)
    carbs_g = carbs_target_g_for(weight_kg=profile.weight_kg, carb_mode=carb_mode)
    fat_g = fat_target_g_for(tdee_kcal=tdee_kcal, protein_g=protein_g, carbs_g=carbs_g)
    return MacroTargets(protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g)


def calculate_training_carbs_g(zones_minutes: Mapping[int, int]) -> float:
    """Return deterministic training fueling carbs as float from normalized zone minutes.

    Contract:
    - Accepts normalized canonical zone keys ``1..5`` with integer minute values.
    - Returns a ``float`` for every valid input.
    - Is pure/deterministic: identical inputs always produce identical outputs.
    """
    total_minutes = sum(zones_minutes.values())
    if total_minutes == 0:
        return 0.0

    if all(minutes == 0 for zone, minutes in zones_minutes.items() if zone != 1):
        return 0.0

    return float(total_minutes)


def select_vo2max_used(
    *,
    age: int,
    gender: Gender,
    weight_kg: float,
    vo2max: int | None,
) -> float:
    """Return explicit VO2max or canonical kg-based prediction when omitted."""
    if vo2max is not None:
        return float(vo2max)

    sex = 0 if gender is Gender.MALE else 1
    return 79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)


def calculate_training_calorie_demand_kcal(
    *,
    age: int,
    gender: Gender,
    weight_kg: float,
    vo2max: int | None,
    zones_minutes: Mapping[int, int],
) -> float:
    """Return VO2-based training calorie demand from normalized zone minutes.

    Contract:
    - Uses explicit ``vo2max`` when present, otherwise the canonical prediction formula.
    - Keeps full floating-point precision internally; rounding is deferred to emitted fields.
    - Applies the fixed zone-intensity coefficients for canonical zones ``1..5``.
    """
    vo2max_used = select_vo2max_used(
        age=age,
        gender=gender,
        weight_kg=weight_kg,
        vo2max=vo2max,
    )
    net_vo2max = max(vo2max_used - 3.5, 0.0)
    base_kcal_per_min = weight_kg * 0.005 * net_vo2max
    return sum(
        float(zones_minutes.get(zone, 0)) * base_kcal_per_min * intensity
        for zone, intensity in ZONE_INTENSITY_BY_ZONE.items()
    )


def calculate_normal_meal_calorie_pool_kcal(
    *,
    tdee_kcal: float,
    training_calorie_demand_kcal: float,
    training_carbs_g: float,
) -> float:
    """Return calories budgeted across the six canonical non-training meals."""
    training_calorie_supply_kcal = round(training_carbs_g * 4.0, 2)
    return round(tdee_kcal + training_calorie_demand_kcal - training_calorie_supply_kcal, 2)


def calculate_periodized_carb_allocation(
    carb_mode: CarbMode,
    daily_carbs_g: float,
    training_before_meal: MealName | None,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> dict[MealName, float]:
    """Return deterministic canonical six-meal carb allocation for Phase 6 entrypoint.

    Phase 6 note:
    - ``LOW`` and ``NORMAL`` carb modes intentionally bypass redistribution rules.
    - Bypass semantics are a temporary placeholder until Phase 7 meal assembly.
    """
    # 1) Non-periodized bypass: return deterministic equal split.
    if carb_mode is not CarbMode.PERIODIZED:
        allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
        _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
        return allocation

    if training_before_meal is None:
        allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
        _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
        return allocation

    # 2) Post-training high-meal rule.
    high_meals = _post_training_high_meals(training_before_meal=training_before_meal)

    # 3) Next-day high-load override, unless explicit conflict.
    high_meals = _apply_tomorrow_high_override(
        high_meals=high_meals,
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
    )

    allocation = _allocation_for_high_meals(
        daily_carbs_g=daily_carbs_g,
        high_meals=high_meals,
    )

    # 4) Reconciliation check.
    _validate_carb_reconciliation(allocation=allocation, daily_carbs_g=daily_carbs_g)
    return allocation


def calculate_meal_split_and_response_payload(
    tdee_kcal: float,
    training_carbs_g: float,
    training_calorie_demand_kcal: float,
    carb_mode: CarbMode,
    training_before_meal: MealName | None,
    training_load_tomorrow: TrainingLoadTomorrow,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict[str, object]:
    """Return canonical response payload from top-level targets and meal budgets."""
    assembly_result = calculate_meal_split_and_response_payload_with_warnings(
        tdee_kcal=tdee_kcal,
        training_carbs_g=training_carbs_g,
        training_calorie_demand_kcal=training_calorie_demand_kcal,
        carb_mode=carb_mode,
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )
    return assembly_result["payload"]


def calculate_meal_split_and_response_payload_with_warnings(
    tdee_kcal: float,
    training_carbs_g: float,
    training_calorie_demand_kcal: float,
    carb_mode: CarbMode,
    training_before_meal: MealName | None,
    training_load_tomorrow: TrainingLoadTomorrow,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> MealAssemblyResult:
    """Return canonical response payload plus non-fatal assembly warnings."""
    normal_meal_calorie_pool_kcal = calculate_normal_meal_calorie_pool_kcal(
        tdee_kcal=tdee_kcal,
        training_calorie_demand_kcal=training_calorie_demand_kcal,
        training_carbs_g=training_carbs_g,
    )

    protein_g_by_meal = _allocate_total_by_canonical_meal_shares(total=protein_g)
    kcal_by_meal = _allocate_total_by_canonical_meal_shares(total=normal_meal_calorie_pool_kcal)
    carbs_strategy_by_meal = _carbs_strategy_by_meal(
        carb_mode=carb_mode,
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
    )

    warnings: list[str] = []
    meal_allocations = [
        _allocation_from_meal_budget(
            meal=meal,
            kcal_budget=kcal_by_meal[meal],
            protein_g=protein_g_by_meal[meal],
            carbs_strategy=carbs_strategy_by_meal[meal],
            warnings=warnings,
        )
        for meal in CANONICAL_MEAL_ORDER
    ]
    validate_meal_allocation_invariants(meal_allocations)

    meals: list[MealPayloadRow] = [
        _serialize_meal_row_with_kcal(
            allocation,
            carbs_strategy=carbs_strategy_by_meal[allocation.meal],
        )
        for allocation in meal_allocations
    ]
    final_protein_g = sum(float(meal.protein_g) for meal in meal_allocations)
    _reconcile_rounded_meal_totals(
        meals=meals,
        protein_g=final_protein_g,
        carbs_g=sum(float(meal.carbs_g) for meal in meal_allocations),
        fat_g=sum(float(meal.fat_g) for meal in meal_allocations),
    )
    _assign_displayed_meal_kcal_shares(
        meals=meals,
        normal_meal_calorie_pool_kcal=normal_meal_calorie_pool_kcal,
    )
    _insert_training_meal_if_needed(
        meals=meals,
        training_carbs_g=training_carbs_g,
        training_before_meal=training_before_meal,
    )
    response_carbs_g = round(sum(float(meal["carbs_g"]) for meal in meals), 2)
    response_fat_g = round(sum(float(meal["fat_g"]) for meal in meals), 2)
    total_kcal = round(sum(float(meal["kcal"]) for meal in meals), 2)

    payload = _assemble_meal_split_response_payload(
        tdee_kcal=tdee_kcal,
        training_carbs_g=training_carbs_g,
        protein_g=round(sum(float(meal["protein_g"]) for meal in meals), 2),
        carbs_g=response_carbs_g,
        fat_g=response_fat_g,
        total_kcal=total_kcal,
        meals=meals,
    )
    return {"payload": payload, "warnings": tuple(warnings)}


def _insert_training_meal_if_needed(
    *,
    meals: list[MealPayloadRow],
    training_carbs_g: float,
    training_before_meal: MealName | None,
) -> None:
    if training_carbs_g <= 0.0:
        return

    training_meal: MealPayloadRow = {
        "meal": "training",
        "carbs_strategy": CarbStrategy.HIGH,
        "carbs_g": training_carbs_g,
        "protein_g": 0.0,
        "fat_g": 0.0,
        "kcal": round(training_carbs_g * 4.0, 2),
    }
    if training_before_meal is None:
        meals.append(training_meal)
        return

    for idx, meal in enumerate(meals):
        if meal["meal"] == training_before_meal:
            meals.insert(idx, training_meal)
            return

    meals.append(training_meal)


def _assemble_meal_split_response_payload(
    *,
    tdee_kcal: float,
    training_carbs_g: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    total_kcal: float,
    meals: list[MealPayloadRow],
) -> dict[str, object]:
    return {
        "TDEE": tdee_kcal,
        "training_carbs_g": training_carbs_g,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "total_kcal": total_kcal,
        "meals": meals,
    }


def _serialize_meal_row_with_kcal(
    allocation: MealAllocation,
    *,
    carbs_strategy: CarbStrategy,
) -> MealPayloadRow:
    carbs_g = round(allocation.carbs_g, 2)
    protein_g = round(allocation.protein_g, 2)
    fat_g = round(allocation.fat_g, 2)
    return {
        "meal": allocation.meal,
        "carbs_strategy": carbs_strategy,
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "kcal": _kcal_from_macros(carbs_g=carbs_g, protein_g=protein_g, fat_g=fat_g),
    }


def _allocation_from_meal_budget(
    *,
    meal: MealName,
    kcal_budget: float,
    protein_g: float,
    carbs_strategy: CarbStrategy,
    warnings: list[str],
) -> MealAllocation:
    allocated_protein_g = protein_g
    protein_kcal = allocated_protein_g * 4.0
    remaining_kcal = kcal_budget - protein_kcal
    if remaining_kcal < 0.0:
        allocated_protein_g = kcal_budget / 4.0
        warnings.append(
            "meal_assembly.protein_reduction: "
            f"reduced {meal.value} protein from {protein_g:.2f}g to {allocated_protein_g:.2f}g "
            f"to fit {kcal_budget:.2f} kcal budget"
        )
        protein_kcal = allocated_protein_g * 4.0
        remaining_kcal = max(kcal_budget - protein_kcal, 0.0)
    carb_calorie_share = CARB_CALORIE_SHARE_BY_STRATEGY[carbs_strategy]
    carbs_g = (remaining_kcal * carb_calorie_share) / 4.0
    fat_g = (remaining_kcal * (1.0 - carb_calorie_share)) / 9.0
    return MealAllocation(
        meal=meal,
        carbs_g=carbs_g,
        protein_g=allocated_protein_g,
        fat_g=fat_g,
    )


def _kcal_from_macros(*, carbs_g: float, protein_g: float, fat_g: float) -> float:
    return round((carbs_g * 4.0) + (protein_g * 4.0) + (fat_g * 9.0), 2)


def _assign_displayed_meal_kcal_shares(
    *,
    meals: list[MealPayloadRow],
    normal_meal_calorie_pool_kcal: float,
) -> None:
    kcal_by_meal = _allocate_total_by_canonical_meal_shares(total=normal_meal_calorie_pool_kcal)
    for meal in meals:
        meal_name = meal["meal"]
        if meal_name == "training":
            continue
        meal["kcal"] = round(kcal_by_meal[cast(MealName, meal_name)], 2)

    displayed_meal_kcal_total = round(sum(float(meal["kcal"]) for meal in meals), 2)
    residual = round(normal_meal_calorie_pool_kcal - displayed_meal_kcal_total, 2)
    if residual == 0.0:
        return

    evening_snack = _get_evening_snack_meal(meals=meals)
    evening_snack["kcal"] = round(float(evening_snack["kcal"]) + residual, 2)


def _reconcile_rounded_meal_totals(
    *,
    meals: list[MealPayloadRow],
    carbs_g: float,
    protein_g: float,
    fat_g: float,
) -> None:
    targets: dict[MacroField, float] = {
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "fat_g": fat_g,
    }
    evening_snack = _get_evening_snack_meal(meals=meals)

    for macro in MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER:
        rounded_total = sum(float(meal[macro]) for meal in meals)
        residual = round(targets[macro] - rounded_total, 2)
        if residual != 0.0:
            evening_snack[macro] = round(float(evening_snack[macro]) + residual, 2)

    for macro in MEAL_ASSEMBLY_RECONCILIATION_MACRO_ORDER:
        reconciled_total = sum(float(meal[macro]) for meal in meals)
        delta = abs(reconciled_total - targets[macro])
        if delta > MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE:
            raise DomainRuleError(
                "meal_assembly.reconciliation: "
                f"sum(meals.{macro})={reconciled_total} "
                f"differs from target={targets[macro]} "
                f"(delta={delta}, tolerance={MEAL_ASSEMBLY_RECONCILIATION_TOLERANCE})"
            )


def _get_evening_snack_meal(*, meals: list[MealPayloadRow]) -> MealPayloadRow:
    for meal in meals:
        if meal["meal"] is MealName.EVENING_SNACK:
            return meal
    raise DomainRuleError("meal_assembly.reconciliation: missing evening-snack meal")


def _allocate_total_by_canonical_meal_shares(*, total: float) -> dict[MealName, float]:
    return {
        meal: total * (share_units / float(CANONICAL_MEAL_SHARE_TOTAL))
        for meal, share_units in zip(CANONICAL_MEAL_ORDER, CANONICAL_MEAL_SHARE_UNITS, strict=True)
    }


def _equal_split_allocation(*, daily_carbs_g: float) -> dict[MealName, float]:
    per_meal_carbs_g = daily_carbs_g / float(len(CANONICAL_MEAL_ORDER))
    return dict.fromkeys(CANONICAL_MEAL_ORDER, per_meal_carbs_g)


def _baseline_carb_strategy_by_meal(*, carb_mode: CarbMode) -> dict[MealName, CarbStrategy]:
    strategy = CarbStrategy.MEDIUM if carb_mode is CarbMode.NORMAL else CarbStrategy.LOW
    return dict.fromkeys(CANONICAL_MEAL_ORDER, strategy)


def _carbs_strategy_by_meal(
    *,
    carb_mode: CarbMode,
    training_before_meal: MealName | None,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> dict[MealName, CarbStrategy]:
    strategy_by_meal = _baseline_carb_strategy_by_meal(carb_mode=carb_mode)
    if carb_mode is not CarbMode.PERIODIZED or training_before_meal is None:
        if carb_mode is CarbMode.PERIODIZED and training_load_tomorrow is TrainingLoadTomorrow.HIGH:
            strategy_by_meal[MealName.DINNER] = CarbStrategy.HIGH
        return strategy_by_meal

    high_meals = _periodized_strategy_high_meals(
        training_before_meal=training_before_meal,
        training_load_tomorrow=training_load_tomorrow,
    )
    for meal in high_meals:
        strategy_by_meal[meal] = CarbStrategy.HIGH

    return strategy_by_meal


def _periodized_strategy_high_meals(
    *,
    training_before_meal: MealName,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> set[MealName]:
    high_meals = {training_before_meal}
    next_high_meal = _next_periodized_high_meal(training_before_meal=training_before_meal)
    if next_high_meal is not None:
        high_meals.add(next_high_meal)

    if training_load_tomorrow is TrainingLoadTomorrow.HIGH:
        high_meals.add(MealName.DINNER)

    return high_meals


def _next_periodized_high_meal(*, training_before_meal: MealName) -> MealName | None:
    if training_before_meal in {MealName.DINNER, MealName.EVENING_SNACK}:
        return None

    current_meal_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
    return CANONICAL_MEAL_ORDER[current_meal_idx + 1]


def _post_training_high_meals(*, training_before_meal: MealName) -> set[MealName]:
    first_high_meal_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
    second_high_meal_idx = (first_high_meal_idx + 1) % len(CANONICAL_MEAL_ORDER)
    return {
        CANONICAL_MEAL_ORDER[first_high_meal_idx],
        CANONICAL_MEAL_ORDER[second_high_meal_idx],
    }


def _apply_tomorrow_high_override(
    *,
    high_meals: set[MealName],
    training_before_meal: MealName,
    training_load_tomorrow: TrainingLoadTomorrow,
) -> set[MealName]:
    conflict_with_tomorrow_high_override = training_before_meal in {
        MealName.DINNER,
        MealName.EVENING_SNACK,
    }
    if (
        training_load_tomorrow == TrainingLoadTomorrow.HIGH
        and not conflict_with_tomorrow_high_override
    ):
        return (high_meals | {MealName.DINNER}) - {MealName.EVENING_SNACK}
    return high_meals


def _allocation_for_high_meals(
    *,
    daily_carbs_g: float,
    high_meals: set[MealName],
) -> dict[MealName, float]:
    allocation = _equal_split_allocation(daily_carbs_g=daily_carbs_g)
    high_meal_carbs_g = 0.30 * daily_carbs_g

    for high_meal in high_meals:
        allocation[high_meal] = high_meal_carbs_g

    remaining_carbs_g = daily_carbs_g - (float(len(high_meals)) * high_meal_carbs_g)
    low_meal_carbs_g = remaining_carbs_g / float(len(CANONICAL_MEAL_ORDER) - len(high_meals))
    for meal in CANONICAL_MEAL_ORDER:
        if meal not in high_meals:
            allocation[meal] = low_meal_carbs_g
    return allocation


def _validate_carb_reconciliation(
    *,
    allocation: dict[MealName, float],
    daily_carbs_g: float,
) -> None:
    total_allocated_carbs = sum(allocation.values())
    delta = abs(total_allocated_carbs - daily_carbs_g)
    if delta > CARB_RECONCILIATION_TOLERANCE:
        raise DomainRuleError(
            "carb_reconciliation: "
            f"sum(allocated_carbs)={total_allocated_carbs} "
            f"differs from daily_carbs_g={daily_carbs_g} "
            f"(delta={delta}, tolerance={CARB_RECONCILIATION_TOLERANCE})"
        )
