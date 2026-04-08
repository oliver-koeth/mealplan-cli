"""Unit tests for UI server configuration defaults."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
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


def _put_json(port: int, path: str, payload: dict[str, Any]) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return response.status, json.loads(response.read().decode("utf-8"))


def _put_json_expect_http_error(port: int, path: str, payload: object) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with pytest.raises(urllib.error.HTTPError) as error_info:
        urllib.request.urlopen(request, timeout=2)  # noqa: S310
    http_error = error_info.value
    parsed = json.loads(http_error.read().decode("utf-8"))
    return http_error.code, parsed


def _get_json(port: int, path: str) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return response.status, json.loads(response.read().decode("utf-8"))


def _get_json_expect_http_error(port: int, path: str) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310
        url=f"http://{ui_server.UI_HOST}:{port}{path}",
        method="GET",
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


def test_ui_server_calendar_put_and_get_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    meal_plan_response_payload: dict[str, Any],
) -> None:
    store_path = tmp_path / "calendar.json"
    monkeypatch.setenv(ui_server.CALENDAR_STORE_PATH_ENV, str(store_path))

    with _running_test_server() as port:
        put_status, put_payload = _put_json(
            port,
            "/api/v1/calendar/20260406",
            meal_plan_response_payload,
        )
        get_status, get_payload = _get_json(port, "/api/v1/calendar/20260406")

    assert put_status == 200
    assert put_payload == {"date": "20260406"}
    assert get_status == 200
    assert get_payload == meal_plan_response_payload
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored == {"20260406": meal_plan_response_payload}


def test_ui_server_calendar_put_overwrites_existing_date_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    meal_plan_response_payload: dict[str, Any],
) -> None:
    store_path = tmp_path / "calendar.json"
    monkeypatch.setenv(ui_server.CALENDAR_STORE_PATH_ENV, str(store_path))
    first_payload = meal_plan_response_payload
    second_payload = json.loads(json.dumps(meal_plan_response_payload))
    second_payload["meals"][0]["carbs_strategy"] = "medium"

    with _running_test_server() as port:
        _put_json(port, "/api/v1/calendar/20260406", first_payload)
        _put_json(port, "/api/v1/calendar/20260406", second_payload)
        _, get_payload = _get_json(port, "/api/v1/calendar/20260406")

    assert get_payload == second_payload


def test_ui_server_calendar_invalid_date_returns_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    meal_plan_response_payload: dict[str, Any],
) -> None:
    monkeypatch.setenv(ui_server.CALENDAR_STORE_PATH_ENV, str(tmp_path / "calendar.json"))

    with _running_test_server() as port:
        status, payload = _put_json_expect_http_error(
            port,
            "/api/v1/calendar/2026-04-06",
            meal_plan_response_payload,
        )

    assert status == 400
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["details"] == [{"field": "date", "message": "expected YYYYMMDD"}]


def test_ui_server_calendar_missing_date_returns_structured_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ui_server.CALENDAR_STORE_PATH_ENV, str(tmp_path / "calendar.json"))

    with _running_test_server() as port:
        status, payload = _get_json_expect_http_error(port, "/api/v1/calendar/20260406")

    assert status == 404
    assert payload["error"]["code"] == "calendar_not_found"
    assert payload["error"]["message"] == "Meal plan not found for requested date."
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["details"] == [
        {"field": "calendar.20260406", "message": "meal plan not found"}
    ]


def test_ui_server_log_post_creates_entry_and_returns_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "food-log.json"
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(store_path))
    payload = {
        "date": "20260408",
        "meal": "breakfast",
        "name": "Eggs",
        "kcal": 210.0,
        "carbs": 2.0,
        "fat": 15.0,
        "protein": 18.0,
        "fiber": 0.0,
    }

    with _running_test_server() as port:
        status, response = _post_json(port, "/api/v1/log", payload)

    assert status == 200
    assert isinstance(response.get("uuid"), str)
    assert response["date"] == "20260408"
    assert response["meal"] == "breakfast"
    assert response["name"] == "Eggs"
    assert response["kcal"] == 210.0
    assert response["carbs"] == 2.0
    assert response["fat"] == 15.0
    assert response["protein"] == 18.0
    assert response["fiber"] == 0.0
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert response["uuid"] in stored


def test_ui_server_log_put_updates_entry_for_uuid_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "food-log.json"
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(store_path))
    create_payload = {
        "date": "20260408",
        "meal": "lunch",
        "name": "Oatmeal",
        "kcal": 320.0,
        "carbs": 52.0,
        "fat": 7.0,
        "protein": 12.0,
        "fiber": 8.0,
    }
    update_payload = {
        "date": "20260408",
        "meal": "dinner",
        "name": "Salmon",
        "kcal": 450.0,
        "carbs": 10.0,
        "fat": 25.0,
        "protein": 48.0,
        "fiber": 0.0,
    }

    with _running_test_server() as port:
        _, created = _post_json(port, "/api/v1/log", create_payload)
        status, response = _put_json(
            port,
            f"/api/v1/log/{created['uuid']}",
            update_payload,
        )

    assert status == 200
    assert response["uuid"] == created["uuid"]
    assert response["meal"] == "dinner"
    assert response["name"] == "Salmon"
    assert response["kcal"] == 450.0
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored[created["uuid"]]["name"] == "Salmon"


def test_ui_server_log_put_unknown_uuid_maps_to_structured_http_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(tmp_path / "food-log.json"))
    payload = {
        "date": "20260408",
        "meal": "lunch",
        "name": "Oatmeal",
        "kcal": 320.0,
        "carbs": 52.0,
        "fat": 7.0,
        "protein": 12.0,
        "fiber": 8.0,
    }

    with _running_test_server() as port:
        status, response = _put_json_expect_http_error(port, "/api/v1/log/missing-uuid", payload)

    assert status == 404
    assert response["error"]["code"] == "log_not_found"
    assert response["error"]["message"] == "Log entry not found."
    assert isinstance(response["error"]["request_id"], str)
    assert response["error"]["details"] == [
        {"field": "log.missing-uuid", "message": "entry not found"}
    ]


def test_ui_server_log_post_invalid_date_maps_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(tmp_path / "food-log.json"))
    payload = {
        "date": "2026-04-08",
        "meal": "breakfast",
        "name": "Eggs",
        "kcal": 210.0,
        "carbs": 2.0,
        "fat": 15.0,
        "protein": 18.0,
        "fiber": 0.0,
    }

    with _running_test_server() as port:
        status, response = _post_json_expect_http_error(port, "/api/v1/log", payload)

    assert status == 400
    assert response["error"]["code"] == "validation_error"
    assert response["error"]["message"] == "Request validation failed."
    assert isinstance(response["error"]["request_id"], str)
    assert response["error"]["details"] == [
        {"field": "date", "message": "Value error, expected YYYYMMDD"}
    ]


def test_ui_server_log_search_supports_optional_and_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "food-log.json"
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(store_path))
    breakfast = {
        "date": "20260408",
        "meal": "breakfast",
        "name": "Greek Yogurt",
        "kcal": 180.0,
        "carbs": 12.0,
        "fat": 8.0,
        "protein": 16.0,
        "fiber": 0.0,
    }
    dinner = {
        "date": "20260408",
        "meal": "dinner",
        "name": "Salmon Bowl",
        "kcal": 420.0,
        "carbs": 35.0,
        "fat": 18.0,
        "protein": 32.0,
        "fiber": 4.0,
    }
    prior_day = {
        "date": "20260407",
        "meal": "dinner",
        "name": "Yogurt Chicken",
        "kcal": 390.0,
        "carbs": 20.0,
        "fat": 14.0,
        "protein": 40.0,
        "fiber": 3.0,
    }

    with _running_test_server() as port:
        _post_json(port, "/api/v1/log", breakfast)
        _post_json(port, "/api/v1/log", dinner)
        _post_json(port, "/api/v1/log", prior_day)
        status, response = _get_json(
            port,
            "/api/v1/log/search?date=20260408&meal=dinner&name=sal",
        )

    assert status == 200
    assert isinstance(response, list)
    assert len(response) == 1
    match = response[0]
    assert isinstance(match["uuid"], str)
    assert match["date"] == "20260408"
    assert match["meal"] == "dinner"
    assert match["name"] == "Salmon Bowl"
    assert match["kcal"] == 420.0
    assert match["carbs"] == 35.0
    assert match["fat"] == 18.0
    assert match["protein"] == 32.0
    assert match["fiber"] == 4.0


def test_ui_server_log_search_invalid_date_maps_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(tmp_path / "food-log.json"))

    with _running_test_server() as port:
        status, response = _get_json_expect_http_error(port, "/api/v1/log/search?date=2026-04-08")

    assert status == 400
    assert response["error"]["code"] == "validation_error"
    assert response["error"]["message"] == "Request validation failed."
    assert isinstance(response["error"]["request_id"], str)
    assert response["error"]["details"] == [
        {"field": "date", "message": "Value error, expected YYYYMMDD"}
    ]


def test_ui_server_log_search_duplicate_query_param_maps_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ui_server.FOOD_LOG_STORE_PATH_ENV, str(tmp_path / "food-log.json"))

    with _running_test_server() as port:
        status, response = _get_json_expect_http_error(
            port,
            "/api/v1/log/search?date=20260408&date=20260409",
        )

    assert status == 400
    assert response["error"]["code"] == "validation_error"
    assert response["error"]["message"] == "Request validation failed."
    assert isinstance(response["error"]["request_id"], str)
    assert response["error"]["details"] == [
        {"field": "date", "message": "expected single query parameter"}
    ]


def test_ui_server_settings_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/settings")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="page">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="false">Calculate</a>' in html
    assert '<a class="nav-link" href="/calendar" aria-current="false">Calendar</a>' in html
    assert '<a class="nav-link" href="/log" aria-current="false">Log</a>' in html
    assert "Athlete profile and defaults" in html


def test_ui_server_settings_shell_includes_typed_settings_controls_and_storage_script() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/settings")

    assert status == 200
    assert '<form class="form-stack" data-settings-form="true">' in html
    assert '<input name="age" type="number" min="1" step="1" required />' in html
    assert '<select name="gender" required>' in html
    assert '<input name="height_cm" type="number" min="1" step="1" required />' in html
    assert '<input name="weight_kg" type="number" min="1" step="0.1" required />' in html
    assert '<input name="vo2max" type="number" min="10" max="100" step="1" />' in html
    assert '<select name="carb_mode" required>' in html
    assert '<select name="activity_level" required>' in html
    assert '<select name="training_load_tomorrow" required>' in html
    assert '<select name="training_before_meal">' in html
    assert '<option value="morning-snack">Morning snack</option>' in html
    assert '<option value="afternoon-snack">Afternoon snack</option>' in html
    assert '<option value="evening-snack">Evening snack</option>' in html
    assert '<option value="training">' not in html
    assert "<h2>UI Settings</h2>" in html
    assert '<select name="ui_theme" required>' in html
    assert '<option value="light">Light</option>' in html
    assert '<option value="dark">Dark</option>' in html
    assert '<select name="ui_language" required>' in html
    assert '<option value="en">English</option>' in html
    assert "const settingsStorageKey = " in html
    assert 'const supportedThemes = new Set(["light", "dark"]);' in html
    assert "applyTheme(persistedTheme);" in html
    assert "documentElement.dataset.theme = resolvedTheme;" in html
    assert 'bindLocalStorageForm(settingsForm, settingsStorageKey,' in html
    assert '"activity_level",' in html
    assert '"training_load_tomorrow",' in html
    assert '"training_before_meal",' in html
    assert '"ui_theme",' in html
    assert '"ui_language",' in html
    assert 'window.localStorage.getItem(storageKey)' in html
    assert 'window.localStorage.setItem(storageKey, JSON.stringify(readValues()));' in html


def test_ui_server_calculate_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/calculate")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="false">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="page">Calculate</a>' in html
    assert '<a class="nav-link" href="/calendar" aria-current="false">Calendar</a>' in html
    assert '<a class="nav-link" href="/log" aria-current="false">Log</a>' in html
    assert "Daily training and meal-plan calculation" in html
    assert '<form class="form-stack" data-settings-form="true">' not in html


def test_ui_server_calendar_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/calendar")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="false">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="false">Calculate</a>' in html
    assert '<a class="nav-link" href="/calendar" aria-current="page">Calendar</a>' in html
    assert '<a class="nav-link" href="/log" aria-current="false">Log</a>' in html
    assert "Date-based meal-plan lookup" in html


def test_ui_server_log_shell_exposes_navigation_and_active_state() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/log")

    assert status == 200
    assert '<header class="app-header">' in html
    assert '<a class="nav-link" href="/settings" aria-current="false">Settings</a>' in html
    assert '<a class="nav-link" href="/calculate" aria-current="false">Calculate</a>' in html
    assert '<a class="nav-link" href="/calendar" aria-current="false">Calendar</a>' in html
    assert '<a class="nav-link" href="/log" aria-current="page">Log</a>' in html
    assert "Food log entry and search" in html


def test_ui_server_calculate_shell_includes_typed_day_controls_and_storage_script() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/calculate")

    assert status == 200
    assert '<form class="form-stack" data-calculate-form="true">' in html
    assert '<select name="activity_level" required>' in html
    assert '<select name="training_load_tomorrow" required>' in html
    assert '<select name="training_before_meal">' in html
    assert 'data-calculate-date-prev="true"' in html
    assert 'data-calculate-date-next="true"' in html
    assert 'name="plan_date"' in html
    assert 'type="date"' in html
    assert '<option value="training">' not in html
    for zone in range(1, 6):
        assert f'name="zone_{zone}_minutes"' in html
        assert 'value="0"' in html
    assert (
        "const guidance = document.querySelector("
        '\'[data-training-before-guidance="true"]\');'
    ) in html
    assert "if (hasTrainingVolume()) {" in html
    assert "trainingBeforeControl.required = true;" in html
    assert "trainingBeforeControl.required = false;" in html
    assert "const calculateStorageKey = " in html
    assert 'bindLocalStorageForm(calculateForm, calculateStorageKey,' in html
    assert "const applyCalculateDefaultsFromSettings = () => {" in html
    assert "const persistedSettings = readLocalStorageObject(settingsStorageKey);" in html
    assert "const defaultFieldNames = [" in html
    assert "applyCalculateDefaultsFromSettings();" in html
    assert "const normalizeCalendarDate = (rawValue) => {" in html
    assert "const isoMatch = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(trimmed);" in html
    assert "if (!dateControl.value) {" in html
    assert "const tomorrowDate = new Date();" in html
    assert "tomorrowDate.setDate(tomorrowDate.getDate() + 1);" in html
    assert "dateControl.value = toIsoDate(tomorrowDate);" in html
    assert 'aria-label="Date"' in html
    assert '<label>Date' not in html
    assert "Calculate inputs are saved automatically in this browser." not in html
    assert "const shiftPlanDate = (deltaDays) => {" in html
    assert 'data-calculate-submit="true"' in html
    assert 'class="alert-card" data-calculate-error-card="true" hidden' in html
    assert 'data-calculate-input-state="true"' in html
    assert 'class="results-state" data-calculate-results-state="true" hidden' in html
    assert 'data-calculate-results="true" hidden' in html
    assert 'data-calculate-results-totals="true"' in html
    assert 'data-calculate-results-meals="true"' in html
    assert 'data-calculate-results-back="true"' in html
    assert 'data-calculate-results-save="true"' in html
    assert 'data-calculate-scale-down="true"' in html
    assert 'data-calculate-scale-up="true"' in html
    assert 'data-calculate-scale-value="true"' in html
    assert 'window.fetch("/api/v1/calculate",' in html
    assert 'if (requestInFlight) {' in html
    assert 'calculateButton.disabled = inFlight;' in html
    assert "let baselineResultsPayload = null;" in html
    assert "let displayedKcalOffset = 0;" in html
    assert "const buildScaledResults = (payload) => {" in html
    assert (
        "const scaleFactor = hasScaleBaseline ? displayedTotalKcal / baselineTotalKcal : 1;"
        in html
    )
    assert "const renderResultsState = () => {" in html
    assert "inputState.hidden = true;" in html
    assert "resultsState.hidden = false;" in html
    assert "const clearResultsState = () => {" in html
    assert "const adjustDisplayedTotalKcal = (deltaKcal) => {" in html
    assert "resultsBackButton.addEventListener" in html
    assert "resultsSaveButton.addEventListener" in html
    assert "void saveDisplayedResults();" in html
    assert "window.fetch(\"/api/v1/calendar/\" + canonicalDate, {" in html
    assert "method: \"PUT\"," in html
    assert "setSaveStatus(\"Saved for \" + canonicalDate + \".\");" in html
    assert "closeResultsState();" in html
    assert "const totals = [" in html
    assert "const meals = [...rawMeals].sort" in html
    assert '["Total kcal", scaledResults.total_kcal, "kcal"]' in html
    assert '["TDEE", scaledResults.TDEE, "kcal"]' in html
    assert '["Carbs", scaledResults.carbs_g, "g"]' in html
    assert '["Fat", scaledResults.fat_g, "g"]' in html
    assert '["Protein", scaledResults.protein_g, "g"]' in html
    assert "const strategyBadgeClass = (value) => {" in html
    assert "strategy-badge strategy-badge-low" in html
    assert "strategy-badge strategy-badge-medium" in html
    assert "strategy-badge strategy-badge-high" in html
    assert "formatStrategyLabel(meal?.carbs_strategy)" in html
    assert "<p>Calories: " in html
    assert "<p>Carbs: " in html
    assert "<p>Fat: " in html
    assert "<p>Protein: " in html
    assert "Displayed total: " in html
    assert "training_load_tomorrow: (" in html
    assert "|| settingsSnapshot.training_load_tomorrow" in html
    assert "training_session: {" in html
    assert "|| settingsSnapshot.training_before_meal" in html
    assert "training_session: {\n              training_load_tomorrow:" not in html
    assert 'training_session: {' in html
    assert '"1": parseMinutes(calculateSnapshot.zone_1_minutes)' in html
    assert 'data-calculate-save-status="true"' in html


def test_ui_server_calendar_shell_includes_date_controls_and_read_only_result_wiring() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/calendar")

    assert status == 200
    assert '<form class="form-stack" data-calendar-form="true">' in html
    assert 'data-calendar-date-prev="true"' in html
    assert 'data-calendar-date-next="true"' in html
    assert 'name="calendar_date"' in html
    assert 'type="date"' in html
    assert 'aria-label="Date"' in html
    assert '<label>Date' not in html
    assert 'data-calendar-status="true"' in html
    assert 'data-calendar-error-card="true" hidden' in html
    assert 'data-calendar-missing-card="true" hidden' in html
    assert 'No meal plan exists, you first need to <a href="/calculate">calculate</a> one.' in html
    assert 'class="results-state" data-calendar-results-state="true" hidden' in html
    assert 'data-calendar-results="true" hidden' in html
    assert 'data-calendar-results-totals="true"' in html
    assert 'data-calendar-results-meals="true"' in html
    assert "const calendarForm = document.querySelector('[data-calendar-form=\"true\"]');" in html
    assert "if (!calendarDateControl.value) {" in html
    assert "calendarDateControl.value = toIsoDate(new Date());" in html
    assert "const canonicalDate = normalizeCalendarDate(calendarDateControl.value);" in html
    assert "window.fetch(\"/api/v1/calendar/\" + canonicalDate, {" in html
    assert 'method: "GET"' in html
    assert "if (response.status === 404) {" in html
    assert "showCalendarMissing();" in html
    assert "calendarDateControl.addEventListener(\"change\", () => {" in html
    assert "void loadCalendarPlan();" in html
    assert "const strategyBadgeClass = (value) => {" in html
    assert "This calendar view is read-only." in html


def test_ui_server_log_shell_includes_entry_search_and_results_regions() -> None:
    with _running_test_server() as port:
        status, html = _get_html(port, "/log")

    assert status == 200
    assert '<form class="form-stack" data-log-entry-form="true">' in html
    assert 'name="uuid" type="text" readonly' in html
    assert 'data-log-date-prev="true"' in html
    assert 'data-log-date-next="true"' in html
    assert 'name="date"' in html
    assert 'name="meal"' in html
    assert 'name="name"' in html
    assert 'name="kcal"' in html
    assert 'name="carbs"' in html
    assert 'name="fat"' in html
    assert 'name="protein"' in html
    assert 'name="fiber"' in html
    assert '<form class="form-stack" data-log-search-form="true">' in html
    assert 'class="log-search-controls"' in html
    assert 'name="date" type="date" aria-label="Search date"' in html
    assert 'name="name" type="text"' in html
    assert 'name="meal"' in html
    assert 'data-log-search-submit="true"' in html
    assert 'data-log-results="true"' in html
    assert (
        "const logEntryForm = document.querySelector('[data-log-entry-form=\"true\"]');"
    ) in html
    assert (
        "const logSearchForm = document.querySelector('[data-log-search-form=\"true\"]');"
    ) in html
    assert "if (!logDateControl.value) {" in html
    assert "logDateControl.value = toIsoDate(new Date());" in html
    assert "if (" in html
    assert "logSearchDateControl" in html
    assert '"value" in logSearchDateControl' in html
    assert "&& !logSearchDateControl.value" in html
    assert "logSearchDateControl.value = toIsoDate(new Date());" in html


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
    assert payload["error"]["details"] == [{"message": "boom"}]


def test_ui_server_calculate_maps_response_validation_error_to_http_422(
    monkeypatch: pytest.MonkeyPatch,
    meal_plan_request_payload: dict[str, Any],
) -> None:
    invalid_response_payload = {
        "TDEE": 1997.19,
        "training_kcal": 512.66,
        "protein_g": 120.0,
        "carbs_g": 240.0,
        "fat_g": 90.0,
        "total_kcal": 2509.84,
        "meals": [
            {
                "meal": "training",
                "carbs_strategy": "high",
                "carbs_g": 60.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "kcal": 240.0,
            },
            {
                "meal": "breakfast",
                "carbs_strategy": "low",
                "carbs_g": 30.0,
                "protein_g": 20.0,
                "fat_g": 15.0,
                "kcal": 450.0,
            },
            {
                "meal": "morning-snack",
                "carbs_strategy": "low",
                "carbs_g": 20.0,
                "protein_g": 10.0,
                "fat_g": 10.0,
                "kcal": 225.0,
            },
            {
                "meal": "lunch",
                "carbs_strategy": "low",
                "carbs_g": 30.0,
                "protein_g": 20.0,
                "fat_g": 15.0,
                "kcal": 450.0,
            },
            {
                "meal": "afternoon-snack",
                "carbs_strategy": "low",
                "carbs_g": 20.0,
                "protein_g": 10.0,
                "fat_g": 10.0,
                "kcal": 225.0,
            },
            {
                "meal": "dinner",
                "carbs_strategy": "low",
                "carbs_g": 30.0,
                "protein_g": 20.0,
                "fat_g": 15.0,
                "kcal": 450.0,
            },
            {
                "meal": "evening-snack",
                "carbs_strategy": "low",
                "carbs_g": 20.0,
                "protein_g": 10.0,
                "fat_g": 25.0,
                "kcal": 469.84,
            },
        ],
    }

    class RaisingCalculationService:
        def calculate(self, request: object) -> MealPlanResponse:
            _ = request
            return MealPlanResponse.model_validate(invalid_response_payload)

    monkeypatch.setattr(ui_server, "MealPlanCalculationService", RaisingCalculationService)

    with _running_test_server() as port:
        status, payload = _post_json_expect_http_error(
            port,
            "/api/v1/calculate",
            meal_plan_request_payload,
        )

    assert status == 422
    assert payload["error"]["code"] == "response_validation_error"
    assert payload["error"]["message"] == "Calculation response validation failed."
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["details"] == [
        {"message": "Value error, total_kcal must equal TDEE + training_kcal"}
    ]


def test_ui_server_calculate_accepts_medium_activity_regression() -> None:
    payload = {
        "age": 18,
        "gender": "male",
        "height_cm": 150,
        "weight_kg": 60.0,
        "activity_level": "medium",
        "carb_mode": "low",
        "training_load_tomorrow": "low",
        "training_session": {
            "zones_minutes": {"1": 10, "2": 20, "3": 30, "4": 0, "5": 0},
            "training_before_meal": "breakfast",
        },
    }

    with _running_test_server() as port:
        status, response = _post_json(port, "/api/v1/calculate", payload)

    assert status == 200
    assert response["TDEE"] == 1997.19
    assert response["training_kcal"] == 512.66
    assert response["total_kcal"] == 2509.85
