"""Domain invariant validation helpers."""

from __future__ import annotations

from mealplan.domain.model import MacroTargets
from mealplan.shared.errors import DomainRuleError


def validate_macro_targets_invariants(macro_targets: MacroTargets) -> None:
    """Enforce hard non-negative invariants for macro-target aggregates."""
    _ensure_non_negative("protein_g", macro_targets.protein_g)
    _ensure_non_negative("carbs_g", macro_targets.carbs_g)
    _ensure_non_negative("fat_g", macro_targets.fat_g)


def _ensure_non_negative(field: str, value: float) -> None:
    if value < 0:
        raise DomainRuleError(f"macro_targets.{field}: must be greater than or equal to 0")
