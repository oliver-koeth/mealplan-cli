"""Tests for domain invariant validation helpers."""

from __future__ import annotations

import pytest

from mealplan.domain.model import MacroTargets
from mealplan.domain.validation import validate_macro_targets_invariants
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_validate_macro_targets_invariants_accepts_non_negative_values() -> None:
    """Non-negative macro targets should satisfy domain invariants."""
    validate_macro_targets_invariants(MacroTargets(protein_g=145.0, carbs_g=290.0, fat_g=70.0))


@pytest.mark.parametrize(
    ("macro_targets", "expected_message"),
    [
        (
            MacroTargets(protein_g=-1.0, carbs_g=290.0, fat_g=70.0),
            "macro_targets.protein_g: must be greater than or equal to 0",
        ),
        (
            MacroTargets(protein_g=145.0, carbs_g=-0.01, fat_g=70.0),
            "macro_targets.carbs_g: must be greater than or equal to 0",
        ),
        (
            MacroTargets(protein_g=145.0, carbs_g=290.0, fat_g=-0.1),
            "macro_targets.fat_g: must be greater than or equal to 0",
        ),
    ],
)
def test_validate_macro_targets_invariants_rejects_negative_values(
    macro_targets: MacroTargets,
    expected_message: str,
) -> None:
    """Negative macro targets should map to deterministic domain rule failures."""
    with pytest.raises(DomainRuleError) as error_info:
        validate_macro_targets_invariants(macro_targets)

    assert str(error_info.value) == expected_message
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN


def test_validate_macro_targets_negative_fat_is_not_validation_error() -> None:
    """Negative-fat outcomes must be classified as domain errors, not input validation."""
    with pytest.raises(DomainRuleError) as error_info:
        validate_macro_targets_invariants(MacroTargets(protein_g=120.0, carbs_g=250.0, fat_g=-1.0))

    assert not isinstance(error_info.value, ValidationError)
