"""Unit tests for UI server configuration defaults."""

from __future__ import annotations

import pytest

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
