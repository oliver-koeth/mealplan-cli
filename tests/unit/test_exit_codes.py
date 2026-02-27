"""Unit tests for shared exception-to-exit-code mapping."""

from mealplan.shared.errors import (
    ConfigError,
    DomainRuleError,
    MealPlanError,
    OutputError,
    ValidationError,
)
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_map_validation_error_to_validation_exit_code() -> None:
    assert map_exception_to_exit_code(ValidationError("bad input")) is ExitCode.VALIDATION


def test_map_domain_error_to_domain_exit_code() -> None:
    assert map_exception_to_exit_code(DomainRuleError("rule failed")) is ExitCode.DOMAIN


def test_map_config_error_to_runtime_exit_code() -> None:
    assert map_exception_to_exit_code(ConfigError("bad config")) is ExitCode.RUNTIME


def test_map_output_error_to_runtime_exit_code() -> None:
    assert map_exception_to_exit_code(OutputError("render failed")) is ExitCode.RUNTIME


def test_map_base_mealplan_error_to_runtime_exit_code() -> None:
    assert map_exception_to_exit_code(MealPlanError("base")) is ExitCode.RUNTIME


def test_map_unhandled_error_to_runtime_exit_code() -> None:
    assert map_exception_to_exit_code(RuntimeError("boom")) is ExitCode.RUNTIME
