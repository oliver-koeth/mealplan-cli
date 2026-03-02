"""Application-layer validation orchestration for meal plan workflows."""

from __future__ import annotations

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.parsing import parse_contract
from mealplan.application.validation import validate_semantic_input
from mealplan.domain.model import MacroTargets, MealAllocation
from mealplan.domain.validation import (
    validate_carb_reconciliation_invariants,
    validate_macro_targets_invariants,
    validate_meal_allocation_invariants,
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
