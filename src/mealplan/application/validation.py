"""Application-level semantic validation for parsed request contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

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

    normalized_zones = normalize_training_zones(
        cast(Mapping[int | str, object], request.training_session.zones_minutes)
    )
    total_zones_minutes = sum(normalized_zones.values())
    if total_zones_minutes > 0 and request.training_session.training_before_meal is None:
        raise ValidationError(
            "training_session.training_before_meal: required when total zones_minutes > 0"
        )


def normalize_training_zones(zones_minutes: Mapping[int | str, object]) -> dict[int, int]:
    """Normalize and validate training zone minutes into canonical 1..5 integer keys."""
    normalized = dict.fromkeys(range(1, 6), 0)

    for raw_zone, raw_minutes in zones_minutes.items():
        zone = _normalize_zone_key(raw_zone)
        minutes = _normalize_zone_minutes(raw_minutes, zone)
        normalized[zone] = minutes

    return normalized


def _normalize_zone_key(zone: object) -> int:
    if isinstance(zone, str):
        if not zone.isdigit():
            raise ValidationError(f"training_session.zones_minutes.{zone}: invalid zone key")
        normalized_zone = int(zone)
    elif isinstance(zone, int):
        normalized_zone = zone
    else:
        raise ValidationError(
            f"training_session.zones_minutes.{zone}: invalid zone key type"
        )

    if normalized_zone < 1 or normalized_zone > 5:
        raise ValidationError(
            f"training_session.zones_minutes.{normalized_zone}: zone must be between 1 and 5"
        )
    return normalized_zone


def _normalize_zone_minutes(minutes: object, zone: int) -> int:
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValidationError(
            f"training_session.zones_minutes.{zone}: minutes must be an integer"
        )
    if minutes < 0:
        raise ValidationError(
            f"training_session.zones_minutes.{zone}: minutes must be greater than or equal to 0"
        )
    return minutes
