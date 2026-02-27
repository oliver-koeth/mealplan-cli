"""Placeholder application use case implementations for CLI scaffolding."""

from __future__ import annotations

from mealplan.shared.errors import ConfigError, DomainRuleError, OutputError, ValidationError


def get_probe_message(simulate_error: str | None = None) -> str:
    """Return deterministic placeholder output for CLI wiring validation."""
    if simulate_error == "validation":
        raise ValidationError("simulated validation failure")
    if simulate_error == "domain":
        raise DomainRuleError("simulated domain rule failure")
    if simulate_error == "config":
        raise ConfigError("simulated configuration failure")
    if simulate_error == "output":
        raise OutputError("simulated output failure")
    if simulate_error == "runtime":
        raise RuntimeError("simulated runtime failure")
    return "mealplan stub: ready"
