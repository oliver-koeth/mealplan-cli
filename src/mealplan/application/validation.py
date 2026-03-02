"""Application-level semantic validation for parsed request contracts."""

from __future__ import annotations

from mealplan.application.contracts import MealPlanRequest
from mealplan.shared.errors import ValidationError


def validate_semantic_input(request: MealPlanRequest) -> None:
    """Validate semantic constraints that are out of scope for schema parsing."""
    if request.age <= 0:
        raise ValidationError("age: must be greater than 0")
    if request.weight_kg <= 0:
        raise ValidationError("weight_kg: must be greater than 0")
