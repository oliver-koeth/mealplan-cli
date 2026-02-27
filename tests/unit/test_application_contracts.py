"""Tests for application boundary contract scaffolding."""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import ProbeRequest, ProbeResponse


def test_probe_request_parses_known_payload() -> None:
    """Request model should accept the placeholder error field shape."""
    request = ProbeRequest.model_validate({"simulate_error": "validation"})
    assert request.simulate_error == "validation"


def test_probe_response_serializes_known_payload() -> None:
    """Response model should serialize the placeholder message field."""
    response = ProbeResponse(message="mealplan stub: ready")
    assert response.model_dump() == {"message": "mealplan stub: ready"}


def test_probe_request_rejects_unknown_fields() -> None:
    """Boundary models should fail when unexpected keys are provided."""
    try:
        ProbeRequest.model_validate({"simulate_error": None, "unexpected": "x"})
    except PydanticValidationError:
        pass
    else:
        raise AssertionError("Expected unknown field validation to fail.")
