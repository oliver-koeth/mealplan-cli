"""Application boundary contracts for placeholder probe flow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, MealName, TrainingLoadTomorrow
from mealplan.domain.model import CANONICAL_MEAL_ORDER

SimulatedErrorKind = Literal["validation", "domain", "config", "output", "runtime"]
TrainingZoneKey = Literal["1", "2", "3", "4", "5"]


class BoundaryModel(BaseModel):
    """Shared base contract for application input/output models."""

    model_config = ConfigDict(extra="forbid")


class TrainingSession(BoundaryModel):
    """Canonical training-session shape for request payloads."""

    zones_minutes: dict[TrainingZoneKey, StrictInt]
    training_before_meal: MealName | None = None


class MealPlanRequest(BoundaryModel):
    """Canonical request DTO for CLI/application parsing."""

    age: StrictInt
    gender: Gender
    weight_kg: StrictFloat
    activity_level: ActivityLevel
    carb_mode: CarbMode
    training_load_tomorrow: TrainingLoadTomorrow
    training_session: TrainingSession | None = None


class MealAllocation(BoundaryModel):
    """Canonical per-meal macro allocation in response payloads."""

    meal: MealName
    carbs_g: StrictFloat
    protein_g: StrictFloat
    fat_g: StrictFloat


class MealPlanResponse(BoundaryModel):
    """Canonical response DTO for application/CLI output payloads."""

    TDEE: StrictFloat
    training_carbs_g: StrictFloat
    protein_g: StrictFloat
    carbs_g: StrictFloat
    fat_g: StrictFloat
    meals: list[MealAllocation]

    @model_validator(mode="after")
    def _ensure_canonical_meal_order(self) -> MealPlanResponse:
        """Require serialized output meal list to follow canonical order exactly."""
        meal_sequence = [entry.meal for entry in self.meals]
        if meal_sequence != list(CANONICAL_MEAL_ORDER):
            raise ValueError("meals must match canonical meal order exactly")
        return self

    @classmethod
    def placeholder(cls) -> MealPlanResponse:
        """Build a zeroed response shape usable before calculation phases are implemented."""
        return cls(
            TDEE=0.0,
            training_carbs_g=0.0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            meals=[
                MealAllocation(meal=meal, carbs_g=0.0, protein_g=0.0, fat_g=0.0)
                for meal in CANONICAL_MEAL_ORDER
            ],
        )


class ProbeRequest(BoundaryModel):
    """Placeholder probe request payload for CLI-to-application boundary."""

    # TODO(phase-2): Extend with real user input fields for planning workflows.
    simulate_error: SimulatedErrorKind | None = Field(
        default=None,
        description="Optional named error path used only for scaffolding tests.",
    )


class ProbeResponse(BoundaryModel):
    """Placeholder probe response payload for application-to-CLI boundary."""

    # TODO(phase-2): Replace message-only shape with structured domain output.
    message: str = Field(description="Deterministic placeholder output.")
