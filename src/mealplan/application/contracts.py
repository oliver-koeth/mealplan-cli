"""Application boundary contracts for placeholder probe flow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from mealplan.domain.enums import ActivityLevel, CarbMode, Gender, MealName, TrainingLoadTomorrow

SimulatedErrorKind = Literal["validation", "domain", "config", "output", "runtime"]


class BoundaryModel(BaseModel):
    """Shared base contract for application input/output models."""

    model_config = ConfigDict(extra="forbid")


class TrainingSession(BoundaryModel):
    """Canonical training-session shape for request payloads."""

    zones_minutes: dict[str, StrictInt]
    training_before_meal: MealName


class MealPlanRequest(BoundaryModel):
    """Canonical request DTO for CLI/application parsing."""

    age: StrictInt
    gender: Gender
    weight_kg: StrictFloat
    activity_level: ActivityLevel
    carb_mode: CarbMode
    training_load_tomorrow: TrainingLoadTomorrow
    training_session: TrainingSession


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
