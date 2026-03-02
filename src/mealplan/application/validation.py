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
    if request.training_session is None:
        return

    total_zones_minutes = sum(request.training_session.zones_minutes.values())
    if total_zones_minutes > 0 and request.training_session.training_before_meal is None:
        raise ValidationError(
            "training_session.training_before_meal: required when total zones_minutes > 0"
        )
