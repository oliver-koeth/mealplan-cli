"""Tests for deterministic application validation orchestration flow."""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import pytest

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.orchestration import (
    MealPlanCalculationService,
    ValidatedTrainingSession,
    _validated_training_session,
    validate_meal_plan_flow,
)
from mealplan.domain.enums import CarbMode
from mealplan.domain.model import MacroTargets, UserProfile
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.shared.exit_codes import ExitCode, map_exception_to_exit_code


def test_meal_plan_calculation_service_has_canonical_api_signature() -> None:
    """Application service should expose a stable calculate(request) contract."""
    signature = inspect.signature(MealPlanCalculationService.calculate)
    type_hints = get_type_hints(MealPlanCalculationService.calculate)

    assert "request" in signature.parameters
    assert type_hints["request"] is MealPlanRequest
    assert type_hints["return"] is MealPlanResponse


def test_meal_plan_calculation_service_calculate_is_deterministic(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Service should return deterministic output for identical typed request input."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()

    first = service.calculate(request)
    second = service.calculate(request)

    assert isinstance(first, MealPlanResponse)
    assert first == second


def test_meal_plan_calculation_service_calculate_runs_validation_before_stages(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation should execute first, before any stage hook runs."""
    steps: list[str] = []
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()

    def fake_validate_meal_plan_flow(
        request_payload: object,
        response: MealPlanResponse,
    ) -> MealPlanRequest:
        assert request_payload is request
        assert isinstance(response, MealPlanResponse)
        steps.append("validate")
        return request

    def track_energy(_: MealPlanRequest) -> float:
        steps.append("energy")
        return 1.0

    def track_macro(_: MealPlanRequest, __: float) -> MacroTargets:
        steps.append("macro")
        return MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0)

    def track_fueling(_: ValidatedTrainingSession) -> float:
        steps.append("fueling")
        return 4.0

    def track_periodization(
        _: MealPlanRequest,
        __: ValidatedTrainingSession,
        ___: MacroTargets,
    ) -> None:
        steps.append("periodization")

    def track_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        steps.append("assembly")
        assert tdee_kcal == 1.0
        assert training_carbs_g == 4.0
        assert macro_targets == MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0)
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_meal_plan_flow",
        fake_validate_meal_plan_flow,
    )
    monkeypatch.setattr(service, "_run_energy_stage", track_energy)
    monkeypatch.setattr(service, "_run_macro_stage", track_macro)
    monkeypatch.setattr(service, "_run_fueling_stage", track_fueling)
    monkeypatch.setattr(service, "_run_periodization_stage", track_periodization)
    monkeypatch.setattr(service, "_run_assembly_stage", track_assembly)

    response = service.calculate(request)

    assert isinstance(response, MealPlanResponse)
    assert steps == ["validate", "energy", "macro", "fueling", "periodization", "assembly"]


def test_meal_plan_calculation_service_calculate_fails_fast_on_validation_error(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation failures should stop all stage execution."""
    steps: list[str] = []
    payload = meal_plan_request_payload
    payload["age"] = 0
    request = MealPlanRequest.model_validate(payload)
    service = MealPlanCalculationService()

    def track_energy(_: MealPlanRequest) -> float:
        steps.append("energy")
        return 1.0

    def track_macro(_: MealPlanRequest, __: float) -> MacroTargets:
        steps.append("macro")
        return MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0)

    def track_fueling(_: ValidatedTrainingSession) -> float:
        steps.append("fueling")
        return 0.0

    def track_periodization(
        _: MealPlanRequest,
        __: ValidatedTrainingSession,
        ___: MacroTargets,
    ) -> None:
        steps.append("periodization")

    def track_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        steps.append("assembly")
        _ = tdee_kcal, training_carbs_g, macro_targets
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(service, "_run_energy_stage", track_energy)
    monkeypatch.setattr(service, "_run_macro_stage", track_macro)
    monkeypatch.setattr(service, "_run_fueling_stage", track_fueling)
    monkeypatch.setattr(service, "_run_periodization_stage", track_periodization)
    monkeypatch.setattr(service, "_run_assembly_stage", track_assembly)

    with pytest.raises(ValidationError) as error_info:
        service.calculate(request)

    assert str(error_info.value) == "age: must be greater than 0"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION
    assert steps == []


def test_meal_plan_calculation_service_uses_normalized_training_for_fueling_and_periodization(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fueling and periodization stage hooks should consume normalized zones from validation."""
    request_payload = meal_plan_request_payload
    request_payload["training_session"]["zones_minutes"] = {"2": 40}
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()
    normalized_sessions: list[ValidatedTrainingSession] = []

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 1.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0),
    )

    def track_fueling_session(training_session: ValidatedTrainingSession) -> float:
        normalized_sessions.append(training_session)
        return 0.0

    monkeypatch.setattr(
        service,
        "_run_fueling_stage",
        track_fueling_session,
    )
    monkeypatch.setattr(
        service,
        "_run_periodization_stage",
        lambda _, training_session, __: normalized_sessions.append(training_session),
    )
    monkeypatch.setattr(
        service,
        "_run_assembly_stage",
        lambda *, tdee_kcal, training_carbs_g, macro_targets: MealPlanResponse.placeholder(),
    )

    service.calculate(request)

    assert len(normalized_sessions) == 2
    for session in normalized_sessions:
        assert session.zones_minutes == {1: 0, 2: 40, 3: 0, 4: 0, 5: 0}


def test_meal_plan_calculation_service_builds_user_profile_and_calls_energy_macro_services(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Energy/macro orchestration should call canonical domain services with typed inputs."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()
    captured: dict[str, object] = {}

    def fake_calculate_tdee_kcal(profile: UserProfile) -> float:
        captured["tdee_profile"] = profile
        return 2451.123456

    def fake_calculate_macro_targets(
        *,
        profile: UserProfile,
        carb_mode: CarbMode,
        tdee_kcal: float,
    ) -> MacroTargets:
        captured["macro_profile"] = profile
        captured["macro_mode"] = carb_mode
        captured["macro_tdee"] = tdee_kcal
        return MacroTargets(protein_g=123.456789, carbs_g=234.567891, fat_g=56.789123)

    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_tdee_kcal",
        fake_calculate_tdee_kcal,
    )
    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_macro_targets",
        fake_calculate_macro_targets,
    )
    monkeypatch.setattr(service, "_run_fueling_stage", lambda _: 0.0)
    monkeypatch.setattr(service, "_run_periodization_stage", lambda _, __, ___: None)
    monkeypatch.setattr(
        service,
        "_run_assembly_stage",
        lambda *, tdee_kcal, training_carbs_g, macro_targets: MealPlanResponse.placeholder(),
    )

    service.calculate(request)

    expected_profile = UserProfile(
        age=request.age,
        gender=request.gender,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        activity_level=request.activity_level,
    )
    assert captured["tdee_profile"] == expected_profile
    assert captured["macro_profile"] == expected_profile
    assert captured["macro_mode"] is request.carb_mode
    assert captured["macro_tdee"] == 2451.123456


def test_meal_plan_calculation_service_passes_unrounded_energy_macro_outputs_downstream(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Energy/macro stage outputs should be forwarded downstream without application rounding."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()
    captured: dict[str, object] = {}
    tdee_value = 2543.987654321
    macro_value = MacroTargets(
        protein_g=143.123456789,
        carbs_g=287.987654321,
        fat_g=61.555555555,
    )

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: tdee_value)
    monkeypatch.setattr(service, "_run_macro_stage", lambda _, __: macro_value)
    monkeypatch.setattr(service, "_run_fueling_stage", lambda _: 0.0)

    def capture_periodization(
        _: MealPlanRequest,
        __: ValidatedTrainingSession,
        macro_targets: MacroTargets,
    ) -> None:
        captured["periodization_macro"] = macro_targets

    def capture_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        captured["assembly_tdee"] = tdee_kcal
        captured["assembly_training_carbs"] = training_carbs_g
        captured["assembly_macro"] = macro_targets
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(service, "_run_periodization_stage", capture_periodization)
    monkeypatch.setattr(service, "_run_assembly_stage", capture_assembly)

    service.calculate(request)

    assert captured["periodization_macro"] == macro_value
    assert captured["assembly_tdee"] == tdee_value
    assert captured["assembly_training_carbs"] == 0.0
    assert captured["assembly_macro"] == macro_value


def test_meal_plan_calculation_service_calls_fueling_service_once_with_canonical_zones(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fueling stage should call the domain service exactly once with canonical zones 1..5."""
    request_payload = meal_plan_request_payload
    request_payload["training_session"]["zones_minutes"] = {"2": 35, "4": 15}
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()
    captured_calls: list[dict[int, int]] = []

    def fake_calculate_training_carbs_g(zones_minutes: dict[int, int]) -> float:
        captured_calls.append(zones_minutes)
        return 50.0

    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_training_carbs_g",
        fake_calculate_training_carbs_g,
    )
    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 1.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0),
    )
    monkeypatch.setattr(service, "_run_periodization_stage", lambda _, __, ___: None)

    response = service.calculate(request)

    assert captured_calls == [{1: 0, 2: 35, 3: 0, 4: 15, 5: 0}]
    assert response.training_carbs_g == 50.0


def test_meal_plan_calculation_service_fueling_zero_training_defaults_to_zero(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted training session should call fueling with canonical zero-training zones."""
    request_payload = meal_plan_request_payload
    request_payload["training_session"] = None
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 1.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0),
    )
    monkeypatch.setattr(service, "_run_periodization_stage", lambda _, __, ___: None)

    response = service.calculate(request)

    assert response.training_carbs_g == 0.0


@pytest.mark.parametrize("carb_mode", ["periodized", "normal"])
def test_meal_plan_calculation_service_omitted_training_defaults_to_zero_training(
    meal_plan_request_payload: dict[str, Any],
    carb_mode: str,
) -> None:
    """Integration coverage: omitted training should stay valid and produce zero training carbs."""
    request_payload = meal_plan_request_payload
    request_payload["carb_mode"] = carb_mode
    request_payload["training_session"] = None
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()

    response = service.calculate(request)

    assert isinstance(response, MealPlanResponse)
    assert response.training_carbs_g == 0.0


def test_validated_training_session_omitted_training_uses_canonical_zero_defaults(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Omitted training should map to explicit canonical defaults for downstream stages."""
    request_payload = meal_plan_request_payload
    request_payload["training_session"] = None
    request = MealPlanRequest.model_validate(request_payload)

    training_session = _validated_training_session(request)

    assert training_session == ValidatedTrainingSession(
        zones_minutes={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        training_before_meal=None,
    )


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
