"""Shared error hierarchy for mealplan CLI and application layers."""


class MealPlanError(Exception):
    """Base error type for controlled mealplan failures."""


class ValidationError(MealPlanError):
    """Raised when user-provided input fails validation."""


class DomainRuleError(MealPlanError):
    """Raised when domain rule checks fail."""


class ConfigError(MealPlanError):
    """Raised when runtime configuration is missing or invalid."""


class OutputError(MealPlanError):
    """Raised when output rendering or writing fails."""
