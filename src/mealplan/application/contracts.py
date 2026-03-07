"""Application boundary contracts for placeholder probe flow."""

from __future__ import annotations

from collections import Counter
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, MealName, TrainingLoadTomorrow
from mealplan.domain.model import CANONICAL_MEAL_ORDER

SimulatedErrorKind = Literal["validation", "domain", "config", "output", "runtime"]
TrainingZoneKey = Literal["1", "2", "3", "4", "5"]
TrainingBeforeMeal = MealName | Literal["training"]
CONTRACT_UNITS_POLICY: Final[dict[str, str]] = {
    "age": "years",
    "height_cm": "cm",
    "weight_kg": "kg",
    "zones_minutes": "minutes",
    "TDEE": "kcal/day (legacy field name retained for compatibility)",
    "training_carbs_g": "g",
    "protein_g": "g",
    "carbs_g": "g",
    "fat_g": "g",
    "total_kcal": "kcal",
    "kcal": "kcal",
}


class BoundaryModel(BaseModel):
    """Shared base contract for application input/output models."""

    model_config = ConfigDict(extra="forbid")


class TrainingSession(BoundaryModel):
    """Canonical training-session shape for request payloads."""

    zones_minutes: dict[TrainingZoneKey, StrictInt] = Field(
        description="Training minutes per zone key ('1'..'5').",
    )
    training_before_meal: TrainingBeforeMeal | None = None


class MealPlanRequest(BoundaryModel):
    """Canonical request DTO for CLI/application parsing."""

    age: StrictInt = Field(description="Age in years.")
    gender: Gender
    height_cm: StrictInt = Field(description="Body height in centimeters.")
    weight_kg: StrictFloat = Field(description="Body weight in kilograms.")
    activity_level: ActivityLevel
    carb_mode: CarbMode
    training_load_tomorrow: TrainingLoadTomorrow
    training_session: TrainingSession | None = None


class MealAllocation(BoundaryModel):
    """Canonical per-meal macro allocation in response payloads."""

    meal: MealName | Literal["training"]
    carbs_g: StrictFloat
    protein_g: StrictFloat
    fat_g: StrictFloat
    kcal: StrictFloat


class MealPlanResponse(BoundaryModel):
    """Canonical response DTO for application/CLI output payloads."""

    TDEE: StrictFloat = Field(
        description=(
            "Legacy output field name representing total daily energy "
            "expenditure (kcal/day)."
        ),
    )
    training_carbs_g: StrictFloat
    protein_g: StrictFloat
    carbs_g: StrictFloat
    fat_g: StrictFloat
    total_kcal: StrictFloat = Field(
        description="Sum of displayed meal kcal values for the planned day.",
    )
    meals: list[MealAllocation]

    @model_validator(mode="after")
    def _ensure_canonical_meal_order(self) -> MealPlanResponse:
        """Require canonical order plus optional single training meal."""
        meal_sequence = [entry.meal for entry in self.meals]
        counts = Counter(meal_sequence)
        training_count = counts["training"]
        if training_count > 1:
            raise ValueError("meals may include at most one training meal")

        canonical_only_sequence = [meal for meal in meal_sequence if meal != "training"]
        if canonical_only_sequence != list(CANONICAL_MEAL_ORDER):
            raise ValueError("meals must match canonical meal order exactly")
        return self

    @model_validator(mode="after")
    def _ensure_total_kcal_matches_meal_sum(self) -> MealPlanResponse:
        displayed_total = round(sum(entry.kcal for entry in self.meals), 2)
        if round(self.total_kcal, 2) != displayed_total:
            raise ValueError("total_kcal must equal sum(meals[*].kcal)")
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
            total_kcal=0.0,
            meals=[
                MealAllocation(meal=meal, carbs_g=0.0, protein_g=0.0, fat_g=0.0, kcal=0.0)
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
