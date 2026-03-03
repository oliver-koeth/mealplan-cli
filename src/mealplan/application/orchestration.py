"""Application-layer validation orchestration for meal plan workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.parsing import parse_contract
from mealplan.application.validation import normalize_training_zones, validate_semantic_input
from mealplan.domain.enums import MealName
from mealplan.domain.model import MacroTargets, MealAllocation
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

        self._run_energy_stage(validated_request)
        self._run_macro_stage(validated_request)
        self._run_fueling_stage(training_session)
        self._run_periodization_stage(validated_request, training_session)
        return self._run_assembly_stage()

    def _run_energy_stage(self, request: MealPlanRequest) -> None:
        """Placeholder energy-stage hook; wired in subsequent Phase 8 stories."""
        _ = request

    def _run_macro_stage(self, request: MealPlanRequest) -> None:
        """Placeholder macro-stage hook; wired in subsequent Phase 8 stories."""
        _ = request

    def _run_fueling_stage(self, training_session: ValidatedTrainingSession) -> None:
        """Placeholder fueling-stage hook using normalized training context."""
        _ = training_session

    def _run_periodization_stage(
        self,
        request: MealPlanRequest,
        training_session: ValidatedTrainingSession,
    ) -> None:
        """Placeholder periodization-stage hook using normalized training context."""
        _ = request, training_session

    def _run_assembly_stage(self) -> MealPlanResponse:
        """Placeholder assembly-stage hook; wired in subsequent Phase 8 stories."""
        return MealPlanResponse.placeholder()


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
