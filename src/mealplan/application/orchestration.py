"""Application-layer validation orchestration for meal plan workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.parsing import parse_contract
from mealplan.application.validation import normalize_training_zones, validate_semantic_input
from mealplan.domain.enums import MealName
from mealplan.domain.model import MacroTargets, MealAllocation, UserProfile
from mealplan.domain.services import (
    calculate_macro_targets,
    calculate_meal_split_and_response_payload,
    calculate_periodized_carb_allocation,
    calculate_tdee_kcal,
    calculate_training_carbs_g,
)
from mealplan.domain.validation import (
    validate_carb_reconciliation_invariants,
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
)


@dataclass(frozen=True, slots=True)
class ValidatedTrainingSession:
    """Normalized training context for downstream orchestration stages."""

    zones_minutes: dict[int, int]
    training_before_meal: MealName | None


class MealPlanCalculationService:
    """Canonical application orchestration boundary for meal plan calculation.

    Phase 8 note:
    - This service method is the only public application entrypoint for calculation.
    - Subsequent Phase 8 stories wire stage composition behind this stable contract.
    """

    def calculate(self, request: MealPlanRequest) -> MealPlanResponse:
        """Run deterministic meal-plan calculation for a validated request."""
        validated_request = validate_meal_plan_flow(
            request_payload=request,
            response=MealPlanResponse.placeholder(),
        )
        training_session = _validated_training_session(validated_request)

        tdee_kcal = self._run_energy_stage(validated_request)
        macro_targets = self._run_macro_stage(validated_request, tdee_kcal)
        training_carbs_g = self._run_fueling_stage(training_session)
        carb_allocation_g_by_meal = self._run_periodization_stage(
            validated_request,
            training_session,
            macro_targets,
        )
        return self._run_assembly_stage(
            tdee_kcal=tdee_kcal,
            training_carbs_g=training_carbs_g,
            macro_targets=macro_targets,
            carb_allocation_g_by_meal=carb_allocation_g_by_meal,
        )

    def _run_energy_stage(self, request: MealPlanRequest) -> float:
        """Return canonical TDEE using typed user-profile input."""
        profile = _user_profile_from_request(request)
        return calculate_tdee_kcal(profile)

    def _run_macro_stage(
        self,
        request: MealPlanRequest,
        tdee_kcal: float,
    ) -> MacroTargets:
        """Return canonical macro targets derived from request carb mode and TDEE."""
        profile = _user_profile_from_request(request)
        return calculate_macro_targets(
            profile=profile,
            carb_mode=request.carb_mode,
            tdee_kcal=tdee_kcal,
        )

    def _run_fueling_stage(self, training_session: ValidatedTrainingSession) -> float:
        """Return canonical training-fuel carbs from normalized training zone minutes."""
        canonical_zones = _canonical_training_zones(training_session.zones_minutes)
        return calculate_training_carbs_g(canonical_zones)

    def _run_periodization_stage(
        self,
        request: MealPlanRequest,
        training_session: ValidatedTrainingSession,
        macro_targets: MacroTargets,
    ) -> dict[MealName, float]:
        """Return canonical meal-level carb allocation from periodization stage."""
        return calculate_periodized_carb_allocation(
            carb_mode=request.carb_mode,
            daily_carbs_g=macro_targets.carbs_g,
            training_before_meal=training_session.training_before_meal,
            training_load_tomorrow=request.training_load_tomorrow,
        )

    def _run_assembly_stage(
        self,
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        macro_targets: MacroTargets,
        carb_allocation_g_by_meal: dict[MealName, float],
    ) -> MealPlanResponse:
        """Return validated response model from canonical meal assembly payload."""
        response_payload = calculate_meal_split_and_response_payload(
            tdee_kcal=tdee_kcal,
            training_carbs_g=training_carbs_g,
            protein_g=macro_targets.protein_g,
            carbs_g=macro_targets.carbs_g,
            fat_g=macro_targets.fat_g,
            carb_allocation_g_by_meal=carb_allocation_g_by_meal,
        )
        return MealPlanResponse.model_validate(response_payload)


def _validated_training_session(request: MealPlanRequest) -> ValidatedTrainingSession:
    if request.training_session is None:
        return ValidatedTrainingSession(
            zones_minutes=dict.fromkeys(range(1, 6), 0),
            training_before_meal=None,
        )
    return ValidatedTrainingSession(
        zones_minutes=normalize_training_zones(
            cast(dict[int | str, object], request.training_session.zones_minutes)
        ),
        training_before_meal=request.training_session.training_before_meal,
    )


def _canonical_training_zones(zones_minutes: dict[int, int]) -> dict[int, int]:
    return {zone: zones_minutes.get(zone, 0) for zone in range(1, 6)}


def _user_profile_from_request(request: MealPlanRequest) -> UserProfile:
    return UserProfile(
        age=request.age,
        gender=request.gender,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        activity_level=request.activity_level,
    )


def validate_meal_plan_flow(
    request_payload: object,
    response: MealPlanResponse,
) -> MealPlanRequest:
    """Run Phase 3 validation flow in deterministic order for all callers."""
    request = parse_contract(MealPlanRequest, request_payload)
    validate_semantic_input(request)
    validate_response_invariants(response)
    return request


def validate_response_invariants(response: MealPlanResponse) -> None:
    """Map response contract data to domain models and enforce domain invariants."""
    macro_targets = MacroTargets(
        protein_g=float(response.protein_g),
        carbs_g=float(response.carbs_g),
        fat_g=float(response.fat_g),
    )
    meal_allocations = [
        MealAllocation(
            meal=allocation.meal,
            carbs_g=float(allocation.carbs_g),
            protein_g=float(allocation.protein_g),
            fat_g=float(allocation.fat_g),
        )
        for allocation in response.meals
    ]

    validate_macro_targets_invariants(macro_targets)
    validate_meal_allocation_invariants(meal_allocations)
    validate_carb_reconciliation_invariants(macro_targets, meal_allocations)
