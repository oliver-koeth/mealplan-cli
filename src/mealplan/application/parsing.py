"""Helpers for parsing boundary DTO payloads into typed contract models."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from mealplan.shared.errors import ValidationError

BoundaryModelT = TypeVar("BoundaryModelT", bound=BaseModel)


def parse_contract(model_cls: type[BoundaryModelT], payload: object) -> BoundaryModelT:
    """Parse a payload into a pydantic contract model with mapped error semantics."""
    try:
        return model_cls.model_validate(payload)
    except PydanticValidationError as error:
        raise ValidationError(_format_validation_error(error)) from None


def _format_validation_error(error: PydanticValidationError) -> str:
    """Create stable user-facing validation detail from the first parse failure."""
    first_error = error.errors()[0]
    path = ".".join(str(part) for part in first_error.get("loc", ()))
    message = first_error.get("msg", "Invalid input.")
    if not path:
        return message
    return f"{path}: {message}"
