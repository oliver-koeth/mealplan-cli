"""Tests for deterministic application validation orchestration flow."""

from __future__ import annotations

import inspect
from typing import Any, cast, get_type_hints

import pytest

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.orchestration import (
    MealPlanCalculationService,
    TrainingDemandContext,
    ValidatedTrainingSession,
    _training_demand_context,
    _validated_training_session,
    validate_meal_plan_flow,
)
from mealplan.domain import calculate_training_calorie_demand_kcal
from mealplan.domain.enums import CarbMode, MealName, TrainingLoadTomorrow
from mealplan.domain.model import CANONICAL_MEAL_ORDER, MacroTargets, UserProfile
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service should return deterministic output for identical typed request input."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()
    canonical_macro_targets = MacroTargets(protein_g=120.0, carbs_g=240.0, fat_g=60.0)

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 2400.0)
    monkeypatch.setattr(service, "_run_macro_stage", lambda _, __: canonical_macro_targets)

    first = service.calculate(request)
    second = service.calculate(request)

    assert isinstance(first, MealPlanResponse)
    assert first == second


def test_meal_plan_calculation_service_resets_warnings_between_runs(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 2400.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=120.0, carbs_g=240.0, fat_g=60.0),
    )
    monkeypatch.setattr(service, "_run_fueling_stage", lambda _: 0.0)
    monkeypatch.setattr(service, "_run_training_demand_stage", lambda *_: 0.0)

    warnings_by_run = iter([("first warning",), ()])

    def track_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        training_calorie_demand_kcal: float,
        carb_mode: CarbMode,
        training_before_meal: MealName | None,
        training_load_tomorrow: TrainingLoadTomorrow,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        _ = (
            tdee_kcal,
            training_carbs_g,
            training_calorie_demand_kcal,
            carb_mode,
            training_before_meal,
            training_load_tomorrow,
            macro_targets,
        )
        service.warnings = next(warnings_by_run)
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(service, "_run_assembly_stage", track_assembly)

    service.calculate(request)
    assert service.warnings == ("first warning",)

    service.calculate(request)
    assert service.warnings == ()


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

    def track_training_demand(_: TrainingDemandContext) -> float:
        steps.append("training-demand")
        return 5.0

    def track_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        training_calorie_demand_kcal: float,
        carb_mode: CarbMode,
        training_before_meal: MealName | None,
        training_load_tomorrow: TrainingLoadTomorrow,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        steps.append("assembly")
        assert tdee_kcal == 1.0
        assert training_carbs_g == 4.0
        assert training_calorie_demand_kcal == 5.0
        assert carb_mode is request.carb_mode
        assert training_before_meal == MealName.LUNCH
        assert training_load_tomorrow is request.training_load_tomorrow
        assert macro_targets == MacroTargets(protein_g=1.0, carbs_g=2.0, fat_g=3.0)
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(
        "mealplan.application.orchestration.validate_meal_plan_flow",
        fake_validate_meal_plan_flow,
    )
    monkeypatch.setattr(service, "_run_energy_stage", track_energy)
    monkeypatch.setattr(service, "_run_macro_stage", track_macro)
    monkeypatch.setattr(service, "_run_fueling_stage", track_fueling)
    monkeypatch.setattr(service, "_run_training_demand_stage", track_training_demand)
    monkeypatch.setattr(service, "_run_assembly_stage", track_assembly)

    response = service.calculate(request)

    assert isinstance(response, MealPlanResponse)
    assert steps == ["validate", "energy", "macro", "fueling", "training-demand", "assembly"]


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

    def track_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        training_calorie_demand_kcal: float,
        carb_mode: CarbMode,
        training_before_meal: MealName | None,
        training_load_tomorrow: TrainingLoadTomorrow,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        steps.append("assembly")
        _ = (
            tdee_kcal,
            training_carbs_g,
            training_calorie_demand_kcal,
            carb_mode,
            training_before_meal,
            macro_targets,
        )
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(service, "_run_energy_stage", track_energy)
    monkeypatch.setattr(service, "_run_macro_stage", track_macro)
    monkeypatch.setattr(service, "_run_fueling_stage", track_fueling)
    monkeypatch.setattr(service, "_run_training_demand_stage", lambda *_: 0.0)
    monkeypatch.setattr(service, "_run_assembly_stage", track_assembly)

    with pytest.raises(ValidationError) as error_info:
        service.calculate(request)

    assert str(error_info.value) == "age: must be greater than 0"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION
    assert steps == []


def test_meal_plan_calculation_service_uses_normalized_training_for_fueling(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fueling stage hooks should consume normalized zones from validation."""
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
        "_run_assembly_stage",
        lambda *,
        tdee_kcal,
        training_carbs_g,
        training_calorie_demand_kcal,
        carb_mode,
        training_before_meal,
        training_load_tomorrow,
        macro_targets: MealPlanResponse.placeholder(),
    )

    service.calculate(request)

    assert len(normalized_sessions) == 1
    for session in normalized_sessions:
        assert session.zones_minutes == {1: 0, 2: 40, 3: 0, 4: 0, 5: 0}


def test_meal_plan_calculation_service_training_demand_stage_passes_athlete_context(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_payload = meal_plan_request_payload
    request_payload["vo2max"] = 58
    request_payload["training_session"]["zones_minutes"] = {"2": 40}
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()
    captured: dict[str, object] = {}

    def fake_calculate_training_calorie_demand_kcal(
        *,
        age: int,
        gender: object,
        weight_kg: float,
        vo2max: int | None,
        zones_minutes: dict[int, int],
    ) -> float:
        captured["age"] = age
        captured["gender"] = gender
        captured["weight_kg"] = weight_kg
        captured["vo2max"] = vo2max
        captured["zones_minutes"] = zones_minutes
        return 123.45

    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_training_calorie_demand_kcal",
        fake_calculate_training_calorie_demand_kcal,
    )

    result = service._run_training_demand_stage(
        _training_demand_context(
            request=request,
            training_session=_validated_training_session(request),
        ),
    )

    assert result == 123.45
    assert captured == {
        "age": request.age,
        "gender": request.gender,
        "weight_kg": request.weight_kg,
        "vo2max": request.vo2max,
        "zones_minutes": {1: 0, 2: 40, 3: 0, 4: 0, 5: 0},
    }


def test_meal_plan_calculation_service_calculate_builds_training_demand_context(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_payload = meal_plan_request_payload
    request_payload["vo2max"] = 57
    request_payload["training_session"]["zones_minutes"] = {"3": 25}
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()
    captured: list[TrainingDemandContext] = []

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 2400.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=120.0, carbs_g=240.0, fat_g=60.0),
    )
    monkeypatch.setattr(service, "_run_fueling_stage", lambda _: 0.0)

    def track_training_demand(context: TrainingDemandContext) -> float:
        captured.append(context)
        return 111.0

    monkeypatch.setattr(service, "_run_training_demand_stage", track_training_demand)

    response = service.calculate(request)

    assert len(captured) == 1
    assert captured[0] == TrainingDemandContext(
        age=request.age,
        gender=request.gender,
        weight_kg=request.weight_kg,
        vo2max=request.vo2max,
        zones_minutes={1: 0, 2: 0, 3: 25, 4: 0, 5: 0},
    )
    assert response.total_kcal > 0.0


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
    monkeypatch.setattr(
        service,
        "_run_assembly_stage",
        lambda *,
        tdee_kcal,
        training_carbs_g,
        training_calorie_demand_kcal,
        carb_mode,
        training_before_meal,
        training_load_tomorrow,
        macro_targets: MealPlanResponse.placeholder(),
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
    monkeypatch.setattr(service, "_run_training_demand_stage", lambda *_: 0.0)

    def capture_assembly(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        training_calorie_demand_kcal: float,
        carb_mode: CarbMode,
        training_before_meal: MealName | None,
        training_load_tomorrow: TrainingLoadTomorrow,
        macro_targets: MacroTargets,
    ) -> MealPlanResponse:
        captured["assembly_tdee"] = tdee_kcal
        captured["assembly_training_carbs"] = training_carbs_g
        captured["assembly_training_demand_kcal"] = training_calorie_demand_kcal
        captured["assembly_carb_mode"] = carb_mode
        captured["assembly_training_before"] = training_before_meal
        captured["assembly_training_load_tomorrow"] = training_load_tomorrow
        captured["assembly_macro"] = macro_targets
        return MealPlanResponse.placeholder()

    monkeypatch.setattr(service, "_run_assembly_stage", capture_assembly)

    service.calculate(request)

    assert captured["assembly_tdee"] == tdee_value
    assert captured["assembly_training_carbs"] == 0.0
    assert captured["assembly_training_demand_kcal"] == 0.0
    assert captured["assembly_carb_mode"] is request.carb_mode
    assert captured["assembly_training_before"] == MealName.LUNCH
    assert captured["assembly_training_load_tomorrow"] is request.training_load_tomorrow
    assert captured["assembly_macro"] == macro_value


def test_meal_plan_calculation_service_periodization_stage_passthroughs_domain_allocation(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application periodization stage should not duplicate/override domain allocation rules."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()
    training_session = _validated_training_session(request)
    macro_targets = MacroTargets(protein_g=100.0, carbs_g=240.0, fat_g=70.0)
    expected_allocation = dict.fromkeys(CANONICAL_MEAL_ORDER, 40.0)

    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_periodized_carb_allocation",
        lambda **_: expected_allocation,
    )

    allocation = service._run_periodization_stage(
        request=request,
        training_session=training_session,
        macro_targets=macro_targets,
    )

    assert allocation == expected_allocation


def test_meal_plan_calculation_service_assembly_stage_calls_domain_meal_split_service(
    meal_plan_response_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assembly stage should delegate payload construction to canonical domain service."""
    service = MealPlanCalculationService()
    macro_targets = MacroTargets(protein_g=155.5, carbs_g=266.6, fat_g=77.7)
    captured: dict[str, object] = {}

    def fake_calculate_meal_split_and_response_payload_with_warnings(
        *,
        tdee_kcal: float,
        training_carbs_g: float,
        training_calorie_demand_kcal: float,
        carb_mode: CarbMode,
        training_before_meal: MealName | None,
        training_load_tomorrow: TrainingLoadTomorrow,
        protein_g: float,
        carbs_g: float,
        fat_g: float,
    ) -> dict[str, Any]:
        captured["tdee_kcal"] = tdee_kcal
        captured["training_carbs_g"] = training_carbs_g
        captured["training_calorie_demand_kcal"] = training_calorie_demand_kcal
        captured["carb_mode"] = carb_mode
        captured["training_before_meal"] = training_before_meal
        captured["training_load_tomorrow"] = training_load_tomorrow
        captured["protein_g"] = protein_g
        captured["carbs_g"] = carbs_g
        captured["fat_g"] = fat_g
        return {"payload": meal_plan_response_payload, "warnings": ("warning",)}

    monkeypatch.setattr(
        "mealplan.application.orchestration.calculate_meal_split_and_response_payload_with_warnings",
        fake_calculate_meal_split_and_response_payload_with_warnings,
    )

    response = service._run_assembly_stage(
        tdee_kcal=2555.123,
        training_carbs_g=61.0,
        training_calorie_demand_kcal=244.0,
        carb_mode=CarbMode.PERIODIZED,
        training_before_meal=MealName.LUNCH,
        training_load_tomorrow=TrainingLoadTomorrow.HIGH,
        macro_targets=macro_targets,
    )

    assert isinstance(response, MealPlanResponse)
    assert captured == {
        "tdee_kcal": 2555.123,
        "training_carbs_g": 61.0,
        "training_calorie_demand_kcal": 244.0,
        "carb_mode": CarbMode.PERIODIZED,
        "training_before_meal": MealName.LUNCH,
        "training_load_tomorrow": TrainingLoadTomorrow.HIGH,
        "protein_g": 155.5,
        "carbs_g": 266.6,
        "fat_g": 77.7,
    }
    assert service.warnings == ("warning",)


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
    response = service.calculate(request)
    expected_training_kcal = round(
        calculate_training_calorie_demand_kcal(
            age=request.age,
            gender=request.gender,
            weight_kg=request.weight_kg,
            vo2max=request.vo2max,
            zones_minutes={1: 0, 2: 35, 3: 0, 4: 15, 5: 0},
        ),
        2,
    )

    assert captured_calls == [{1: 0, 2: 35, 3: 0, 4: 15, 5: 0}]
    assert response.training_kcal == pytest.approx(expected_training_kcal)


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
    response = service.calculate(request)

    assert response.training_kcal == 0.0


@pytest.mark.parametrize("carb_mode", ["periodized", "normal"])
def test_meal_plan_calculation_service_omitted_training_defaults_to_zero_training(
    meal_plan_request_payload: dict[str, Any],
    carb_mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration coverage: omitted training should stay valid and produce zero training kcal."""
    request_payload = meal_plan_request_payload
    request_payload["carb_mode"] = carb_mode
    request_payload["training_session"] = None
    request = MealPlanRequest.model_validate(request_payload)
    service = MealPlanCalculationService()
    canonical_macro_targets = MacroTargets(protein_g=120.0, carbs_g=240.0, fat_g=60.0)

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 2400.0)
    monkeypatch.setattr(service, "_run_macro_stage", lambda _, __: canonical_macro_targets)
    response = service.calculate(request)

    assert isinstance(response, MealPlanResponse)
    assert response.training_kcal == 0.0


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


@pytest.mark.parametrize(
    ("scenario_payload", "expected_training_carbs_g"),
    [
        (
            {
                "age": 18,
                "gender": "male",
                "height_cm": 160,
                "weight_kg": 61.5,
                "activity_level": "medium",
                "carb_mode": "periodized",
                "training_load_tomorrow": "high",
                "training_session": {
                    "zones_minutes": {"1": 20, "2": 40, "3": 0, "4": 0, "5": 0},
                    "training_before_meal": "lunch",
                },
            },
            60.0,
        ),
        (
            {
                "age": 18,
                "gender": "male",
                "height_cm": 160,
                "weight_kg": 60.5,
                "activity_level": "medium",
                "carb_mode": "normal",
                "training_load_tomorrow": "high",
                "training_session": {
                    "zones_minutes": {"1": 20, "2": 40, "3": 0, "4": 0, "5": 0},
                    "training_before_meal": "lunch",
                },
            },
            60.0,
        ),
        (
            {
                "age": 18,
                "gender": "male",
                "height_cm": 160,
                "weight_kg": 60.5,
                "activity_level": "medium",
                "carb_mode": "normal",
                "training_load_tomorrow": "high",
                "training_session": {
                    "zones_minutes": {"1": 30, "2": 0, "3": 0, "4": 0, "5": 0},
                    "training_before_meal": "lunch",
                },
            },
            0.0,
        ),
        (
            {
                "age": 18,
                "gender": "male",
                "height_cm": 160,
                "weight_kg": 60.5,
                "activity_level": "medium",
                "carb_mode": "normal",
                "training_load_tomorrow": "high",
                "training_session": None,
            },
            0.0,
        ),
    ],
    ids=[
        "periodized-with-training",
        "non-periodized-with-training",
        "zone-1-only-training",
        "omitted-training-session",
    ],
)
def test_meal_plan_calculation_service_integration_success_matrix(
    scenario_payload: dict[str, object],
    expected_training_carbs_g: float,
) -> None:
    """Integration matrix: representative successful calculate(...) scenarios."""
    request = MealPlanRequest.model_validate(scenario_payload)
    response = MealPlanCalculationService().calculate(request)

    assert isinstance(response, MealPlanResponse)
    expected_meal_sequence: list[MealName | str] = list(CANONICAL_MEAL_ORDER)
    if expected_training_carbs_g > 0.0 and request.training_session is not None:
        insertion_idx = expected_meal_sequence.index(request.training_session.training_before_meal)
        expected_meal_sequence.insert(insertion_idx, "training")
    assert [meal.meal for meal in response.meals] == expected_meal_sequence
    assert len(response.meals) == len(expected_meal_sequence)

    canonical_meals = [meal for meal in response.meals if meal.meal != "training"]
    training_meals = [meal for meal in response.meals if meal.meal == "training"]

    carbs_total = sum(meal.carbs_g for meal in response.meals)
    protein_total = sum(meal.protein_g for meal in canonical_meals)
    fat_total = sum(meal.fat_g for meal in canonical_meals)
    assert carbs_total == pytest.approx(response.carbs_g)
    assert protein_total == pytest.approx(response.protein_g)
    assert fat_total == pytest.approx(response.fat_g)
    if expected_training_carbs_g > 0.0:
        assert len(training_meals) == 1
        assert training_meals[0].carbs_strategy == "high"
        assert training_meals[0].carbs_g == pytest.approx(expected_training_carbs_g)
        assert training_meals[0].protein_g == 0.0
        assert training_meals[0].fat_g == 0.0
        assert training_meals[0].kcal == round(expected_training_carbs_g * 4.0, 2)
    else:
        assert training_meals == []

    expected_canonical_strategies = ["medium"] * 6 if request.carb_mode == "normal" else ["low"] * 6
    if request.carb_mode == "periodized" and request.training_session is not None:
        training_before_meal = cast(MealName, request.training_session.training_before_meal)
        training_before_idx = CANONICAL_MEAL_ORDER.index(training_before_meal)
        expected_canonical_strategies[training_before_idx] = "high"
        if training_before_meal not in {MealName.DINNER, MealName.EVENING_SNACK}:
            expected_canonical_strategies[training_before_idx + 1] = "high"
        if request.training_load_tomorrow == "high":
            expected_canonical_strategies[CANONICAL_MEAL_ORDER.index(MealName.DINNER)] = "high"

    assert [meal.carbs_strategy for meal in canonical_meals] == expected_canonical_strategies

    for meal in response.meals:
        assert isinstance(meal.kcal, float)
    assert response.total_kcal == pytest.approx(sum(meal.kcal for meal in response.meals))
    expected_training_calorie_demand = 0.0
    if request.training_session is not None:
        expected_training_calorie_demand = calculate_training_calorie_demand_kcal(
            age=request.age,
            gender=request.gender,
            weight_kg=request.weight_kg,
            vo2max=request.vo2max,
            zones_minutes={
                zone: int(request.training_session.zones_minutes.get(str(zone), 0))
                for zone in range(1, 6)
            },
        )
    assert response.training_kcal == pytest.approx(round(expected_training_calorie_demand, 2))
    assert sum(meal.kcal for meal in response.meals) == pytest.approx(
        response.TDEE + expected_training_calorie_demand
    )


@pytest.mark.parametrize(
    ("training_before_meal", "training_load_tomorrow", "expected_strategies"),
    [
        ("dinner", "medium", ["low", "low", "low", "low", "high", "low"]),
        ("dinner", "high", ["low", "low", "low", "low", "high", "low"]),
        ("evening-snack", "medium", ["low", "low", "low", "low", "low", "high"]),
        ("evening-snack", "high", ["low", "low", "low", "low", "high", "high"]),
    ],
)
def test_meal_plan_calculation_service_integration_periodized_late_day_strategies(
    meal_plan_request_payload: dict[str, Any],
    training_before_meal: str,
    training_load_tomorrow: str,
    expected_strategies: list[str],
) -> None:
    payload = meal_plan_request_payload
    payload["carb_mode"] = "periodized"
    payload["training_load_tomorrow"] = training_load_tomorrow
    payload["training_session"] = {
        "zones_minutes": {"1": 0, "2": 40, "3": 0, "4": 0, "5": 0},
        "training_before_meal": training_before_meal,
    }

    request = MealPlanRequest.model_validate(payload)
    response = MealPlanCalculationService().calculate(request)

    canonical_meals = [meal for meal in response.meals if meal.meal != "training"]
    assert [meal.carbs_strategy for meal in canonical_meals] == expected_strategies


def test_meal_plan_calculation_service_integration_surfaces_protein_reduction_warnings(
    meal_plan_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    service = MealPlanCalculationService()

    monkeypatch.setattr(service, "_run_energy_stage", lambda _: 600.0)
    monkeypatch.setattr(
        service,
        "_run_macro_stage",
        lambda _, __: MacroTargets(protein_g=180.0, carbs_g=200.0, fat_g=40.0),
    )
    monkeypatch.setattr(service, "_run_fueling_stage", lambda _: 0.0)
    monkeypatch.setattr(service, "_run_training_demand_stage", lambda *_: 0.0)

    response = service.calculate(request)

    assert service.warnings == (
        "meal_assembly.protein_reduction: reduced breakfast protein from 40.00g to 33.33g "
        "to fit 133.33 kcal budget",
        "meal_assembly.protein_reduction: reduced morning-snack protein from 20.00g to 16.67g "
        "to fit 66.67 kcal budget",
        "meal_assembly.protein_reduction: reduced lunch protein from 40.00g to 33.33g "
        "to fit 133.33 kcal budget",
        "meal_assembly.protein_reduction: reduced afternoon-snack protein from 20.00g to 16.67g "
        "to fit 66.67 kcal budget",
        "meal_assembly.protein_reduction: reduced dinner protein from 40.00g to 33.33g "
        "to fit 133.33 kcal budget",
        "meal_assembly.protein_reduction: reduced evening-snack protein from 20.00g to 16.67g "
        "to fit 66.67 kcal budget",
    )
    assert response.protein_g == pytest.approx(150.0)
    assert response.carbs_g == pytest.approx(0.0)
    assert response.fat_g == pytest.approx(0.0)
    assert all(meal.carbs_g >= 0.0 for meal in response.meals)
    assert all(meal.fat_g >= 0.0 for meal in response.meals)


def test_meal_plan_calculation_service_integration_validation_failure(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Integration matrix: semantic validation failure propagates from calculate(...)."""
    payload = meal_plan_request_payload
    payload["age"] = 0
    request = MealPlanRequest.model_validate(payload)

    with pytest.raises(ValidationError) as error_info:
        MealPlanCalculationService().calculate(request)

    assert str(error_info.value) == "age: must be greater than 0"
    assert map_exception_to_exit_code(error_info.value) is ExitCode.VALIDATION


def test_meal_plan_calculation_service_integration_meal_assembly_reconciliation_tolerance(
    meal_plan_request_payload: dict[str, Any],
) -> None:
    """Integration matrix: sub-cent reconciliation drift is accepted within tolerance."""
    request = MealPlanRequest.model_validate(meal_plan_request_payload)
    response = MealPlanCalculationService().calculate(request)

    assert isinstance(response, MealPlanResponse)

    fat_total = sum(meal.fat_g for meal in response.meals)
    assert abs(fat_total - response.fat_g) <= 1e-2


@pytest.mark.parametrize(
    ("carb_mode", "expected_canonical_strategies"),
    [
        ("normal", ["medium"] * 6),
        ("low", ["low"] * 6),
        ("periodized", ["low"] * 6),
    ],
)
def test_meal_plan_calculation_service_integration_uses_emitted_meal_totals_and_baseline_strategies(
    meal_plan_request_payload: dict[str, Any],
    carb_mode: str,
    expected_canonical_strategies: list[str],
) -> None:
    payload = meal_plan_request_payload
    payload["carb_mode"] = carb_mode
    payload["training_load_tomorrow"] = "medium"
    payload["training_session"] = None

    request = MealPlanRequest.model_validate(payload)
    response = MealPlanCalculationService().calculate(request)

    canonical_meals = [meal for meal in response.meals if meal.meal != "training"]

    assert [meal.carbs_strategy for meal in canonical_meals] == expected_canonical_strategies
    assert response.training_kcal == 0.0
    assert response.carbs_g == pytest.approx(sum(meal.carbs_g for meal in canonical_meals))
    assert response.fat_g == pytest.approx(sum(meal.fat_g for meal in canonical_meals))
