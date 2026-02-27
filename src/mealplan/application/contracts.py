"""Application boundary contracts for placeholder probe flow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SimulatedErrorKind = Literal["validation", "domain", "config", "output", "runtime"]


class BoundaryModel(BaseModel):
    """Shared base contract for application input/output models."""

    model_config = ConfigDict(extra="forbid")


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
