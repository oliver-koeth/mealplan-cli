"""Unit tests for UI server configuration defaults."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from mealplan.application.contracts import MealPlanResponse
from mealplan.shared.errors import DomainRuleError, ValidationError
from mealplan.web import ui_server


def test_ui_server_default_port_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ui_server.UI_PORT_START_ENV, raising=False)
    monkeypatch.delenv(ui_server.UI_PORT_END_ENV, raising=False)

    assert ui_server._resolve_port_window() == (8765, 8775)


def test_ui_server_port_window_respects_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ui_server.UI_PORT_START_ENV, "30000")
    monkeypatch.setenv(ui_server.UI_PORT_END_ENV, "30002")

    assert ui_server._resolve_port_window() == (30000, 30002)


def test_ui_server_invalid_port_window_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ui_server.UI_PORT_START_ENV, "30010")
    monkeypatch.setenv(ui_server.UI_PORT_END_ENV, "30009")

    with pytest.raises(RuntimeError, match="invalid port window 30010..30009"):
        ui_server._resolve_port_window()


@contextmanager
def _running_test_server() -> Iterator[int]:
    server = ui_server._UiServer((ui_server.UI_HOST, 0))
    _, port = server.server_address[:2]
    server_port = int(port)
    serve_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    serve_thread.start()
    try:
        yield server_port
    finally:
        server.shutdown()
        server.server_close()
        serve_thread.join(timeout=2)


def _post_json(port: int, path: str, payload: dict[str, Any]) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return response.status, json.loads(response.read().decode("utf-8"))


def _post_json_expect_http_error(port: int, path: str, payload: object) -> tuple[int, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error_info:
        urllib.request.urlopen(request, timeout=2)  # noqa: S310
    http_error = error_info.value
    parsed = json.loads(http_error.read().decode("utf-8"))
    return http_error.code, parsed


def _get_html(port: int, path: str) -> tuple[int, str]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return response.status, response.read().decode("utf-8")


def test_ui_server_calculate_endpoint_returns_canonical_response_shape(
    monkeypatch: pytest.MonkeyPatch,
    meal_plan_request_payload: dict[str, Any],
    meal_plan_response_payload: dict[str, Any],
) -> None:
    expected_response = MealPlanResponse.model_validate(meal_plan_response_payload)

    class FakeCalculationService:
        called_with: list[object] = []

        def calculate(self, request: object) -> MealPlanResponse:
            self.called_with.append(request)
            return expected_response

    monkeypatch.setattr(ui_server, "MealPlanCalculationService", FakeCalculationService)

    with _running_test_server() as port:
        status, payload = _post_json(port, "/api/v1/calculate", meal_plan_request_payload)

    assert status == 200
    assert payload == meal_plan_response_payload


def test_ui_server_settings_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/settings")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="page">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="false">Calculate</a>' in html
    assert "Athlete profile and defaults" in html


def test_ui_server_calculate_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/calculate")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="false">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="page">Calculate</a>' in html
    assert "Daily training and meal-plan calculation" in html


def test_ui_server_calculate_maps_validation_error_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
    meal_plan_request_payload: dict[str, Any],
) -> None:
    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            raise ValidationError("training_session.training_before_meal: field required")

    monkeypatch.setattr(ui_server, "MealPlanCalculationService", FakeCalculationService)

    with _running_test_server() as port:
        status, payload = _post_json_expect_http_error(
            port,
            "/api/v1/calculate",
            meal_plan_request_payload,
        )

    assert status == 400
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["details"] == [
        {"field": "training_session.training_before_meal", "message": "field required"}
    ]


def test_ui_server_calculate_maps_domain_rule_error_to_http_422(
    monkeypatch: pytest.MonkeyPatch,
    meal_plan_request_payload: dict[str, Any],
) -> None:
    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            raise DomainRuleError("meal_assembly.reconciliation: unable to reconcile totals")

    monkeypatch.setattr(ui_server, "MealPlanCalculationService", FakeCalculationService)

    with _running_test_server() as port:
        status, payload = _post_json_expect_http_error(
            port,
            "/api/v1/calculate",
            meal_plan_request_payload,
        )

    assert status == 422
    assert payload["error"]["code"] == "domain_rule_error"
    assert payload["error"]["message"] == "Meal-plan domain rule failed."
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["details"] == [
        {"field": "meal_assembly.reconciliation", "message": "unable to reconcile totals"}
    ]


def test_ui_server_calculate_maps_unexpected_error_to_http_500(
    monkeypatch: pytest.MonkeyPatch,
    meal_plan_request_payload: dict[str, Any],
) -> None:
    class FakeCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            raise RuntimeError("boom")

    monkeypatch.setattr(ui_server, "MealPlanCalculationService", FakeCalculationService)

    with _running_test_server() as port:
        status, payload = _post_json_expect_http_error(
            port,
            "/api/v1/calculate",
            meal_plan_request_payload,
        )

    assert status == 500
    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["message"] == "Internal server error."
    assert isinstance(payload["error"]["request_id"], str)
    assert "details" not in payload["error"]
