"""Tests for deterministic application validation orchestration flow."""

from __future__ import annotations

from typing import Any

import pytest

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.orchestration import validate_meal_plan_flow
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_validate_meal_plan_flow_runs_schema_semantic_then_domain_checks(
    meal_plan_request_payload: dict[str, Any],
    meal_plan_response_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation flow should execute parse -> semantic -> domain invariants in order."""
    steps: list[str] = []

    def fake_parse_contract(model_cls: type[MealPlanRequest], payload: object) -> MealPlanRequest:
        assert model_cls is MealPlanRequest
        assert payload is meal_plan_request_payload
        steps.append("parse")
        return MealPlanRequest.model_validate(payload)

    def fake_validate_semantic_input(request: MealPlanRequest) -> None:
        assert isinstance(request, MealPlanRequest)
        steps.append("semantic")

    def fake_validate_macro_targets_invariants(_: object) -> None:
        steps.append("domain-macro")

    def fake_validate_meal_allocation_invariants(_: object) -> None:
        steps.append("domain-meals")

    def fake_validate_carb_reconciliation_invariants(_: object, __: object) -> None:
        steps.append("domain-carb")

    monkeypatch.setattr("mealplan.application.orchestration.parse_contract", fake_parse_contract)
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_semantic_input",
        fake_validate_semantic_input,
    )
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_macro_targets_invariants",
        fake_validate_macro_targets_invariants,
    )
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_meal_allocation_invariants",
        fake_validate_meal_allocation_invariants,
    )
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_carb_reconciliation_invariants",
        fake_validate_carb_reconciliation_invariants,
    )

    response = MealPlanResponse.model_validate(meal_plan_response_payload)

    request = validate_meal_plan_flow(meal_plan_request_payload, response)

    assert isinstance(request, MealPlanRequest)
    assert steps == ["parse", "semantic", "domain-macro", "domain-meals", "domain-carb"]


def test_validate_meal_plan_flow_parse_failure_stops_later_phases(
    meal_plan_response_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema failures should prevent semantic and domain validation execution."""
    steps: list[str] = []

    def fail_parse_contract(_: type[MealPlanRequest], __: object) -> MealPlanRequest:
        raise ValidationError("age: Input should be a valid integer")

    def track_semantic(_: MealPlanRequest) -> None:
        steps.append("semantic")

    def track_domain(_: object) -> None:
        steps.append("domain")

    monkeypatch.setattr("mealplan.application.orchestration.parse_contract", fail_parse_contract)
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_semantic_input",
        track_semantic,
    )
    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_macro_targets_invariants",
        track_domain,
    )

    response = MealPlanResponse.model_validate(meal_plan_response_payload)

    with pytest.raises(ValidationError) as error_info:
        validate_meal_plan_flow({"age": "bad"}, response)

    assert str(error_info.value) == "age: Input should be a valid integer"
    assert steps == []


def test_validate_meal_plan_flow_semantic_failure_stops_domain_checks(
    meal_plan_request_payload: dict[str, Any],
    meal_plan_response_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic failures should map to validation errors before domain checks run."""
    steps: list[str] = []

    def track_domain(_: object) -> None:
        steps.append("domain")

    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_macro_targets_invariants",
        track_domain,
    )

    payload = meal_plan_request_payload
    payload["age"] = 0
    response = MealPlanResponse.model_validate(meal_plan_response_payload)

    with pytest.raises(ValidationError) as error_info:
        validate_meal_plan_flow(payload, response)

    assert str(error_info.value) == "age: must be greater than 0"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION
    assert steps == []


def test_validate_meal_plan_flow_surfaces_domain_errors(
    meal_plan_request_payload: dict[str, Any],
    meal_plan_response_payload: dict[str, Any],
) -> None:
    """Domain invariant failures should be raised as DomainRuleError."""
    response_payload = meal_plan_response_payload
    response_payload["fat_g"] = -0.1
    response = MealPlanResponse.model_validate(response_payload)

    with pytest.raises(DomainRuleError) as error_info:
        validate_meal_plan_flow(meal_plan_request_payload, response)

    assert str(error_info.value) == "macro_targets.fat_g: must be greater than or equal to 0"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.DOMAIN
    assert not isinstance(error_info.value, ValidationError)
