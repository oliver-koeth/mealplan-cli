"""Placeholder application use case implementations for CLI scaffolding."""

from __future__ import annotations

from mealplan.application.contracts import ProbeRequest, ProbeResponse
from mealplan.shared.errors import ConfigError, DomainRuleError, OutputError, ValidationError


def run_probe(request: ProbeRequest) -> ProbeResponse:
    """Return deterministic placeholder output for CLI wiring validation."""
    if request.simulate_error == "validation":
        raise ValidationError("simulated validation failure")
    if request.simulate_error == "domain":
        raise DomainRuleError("simulated domain rule failure")
    if request.simulate_error == "config":
        raise ConfigError("simulated configuration failure")
    if request.simulate_error == "output":
        raise OutputError("simulated output failure")
    if request.simulate_error == "runtime":
        raise RuntimeError("simulated runtime failure")
    return ProbeResponse(message="mealplan stub: ready")
