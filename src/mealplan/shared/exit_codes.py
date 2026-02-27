"""Canonical process exit codes and error mapping helpers."""

from __future__ import annotations

from enum import IntEnum

from mealplan.shared.errors import (
    ConfigError,
    DomainRuleError,
    MealPlanError,
    OutputError,
    ValidationError,
)


class ExitCode(IntEnum):
    """Canonical process exit codes for mealplan commands."""

    SUCCESS = 0
    VALIDATION = 2
    DOMAIN = 3
    RUNTIME = 4


def map_exception_to_exit_code(error: Exception) -> ExitCode:
    """Map known exception types to a canonical process exit code."""
    if isinstance(error, ValidationError):
        return ExitCode.VALIDATION
    if isinstance(error, DomainRuleError):
        return ExitCode.DOMAIN
    if isinstance(error, (ConfigError, OutputError, MealPlanError)):
        return ExitCode.RUNTIME
    return ExitCode.RUNTIME
