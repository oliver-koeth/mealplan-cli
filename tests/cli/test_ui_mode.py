"""CLI tests for local UI server mode startup and lifecycle."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

UI_HOST = "127.0.0.1"
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"


@contextmanager
def _reserve_ports(ports: range) -> Iterator[None]:
    sockets: list[socket.socket] = []
    try:
        for port in ports:
            reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            reservation.bind((UI_HOST, port))
            reservation.listen(1)
            sockets.append(reservation)
        yield
    finally:
        for reservation in sockets:
            reservation.close()


def _ui_command() -> list[str]:
    return [sys.executable, "-m", "mealplan", "--ui"]


def _find_consecutive_free_ports(count: int = 2) -> tuple[int, int]:
    for start in range(20000, 50000):
        reservations: list[socket.socket] = []
        try:
            for port in range(start, start + count):
                reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                reservation.bind((UI_HOST, port))
                reservation.listen(1)
                reservations.append(reservation)
        except OSError:
            for reservation in reservations:
                reservation.close()
            continue
        for reservation in reservations:
            reservation.close()
        return start, start + count - 1
    raise AssertionError("Unable to find a free local test port window")


def _discover_live_ui_port(*, port_start: int, port_end: int, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port in range(port_start, port_end + 1):
            try:
                with urllib.request.urlopen(  # noqa: S310
                    f"http://{UI_HOST}:{port}/api/v1/health", timeout=0.2
                ) as response:
                    if response.status == 200:
                        return port
            except Exception:  # noqa: BLE001
                continue
        time.sleep(0.1)
    raise AssertionError("UI server did not become reachable in time")


def test_ui_mode_starts_on_fallback_port_serves_shell_and_health_then_gracefully_stops() -> None:
    port_start, port_end = _find_consecutive_free_ports(count=2)
    env = os.environ | {
        "PYTHONUNBUFFERED": "1",
        UI_PORT_START_ENV: str(port_start),
        UI_PORT_END_ENV: str(port_end),
    }

    with _reserve_ports(range(port_start, port_start + 1)):
        process = subprocess.Popen(  # noqa: S603
            _ui_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            assert process.poll() is None
            port = _discover_live_ui_port(port_start=port_start, port_end=port_end)
            assert port == port_end

            with urllib.request.urlopen(  # noqa: S310
                f"http://{UI_HOST}:{port}/calculate", timeout=2
            ) as shell_response:
                shell_html = shell_response.read().decode("utf-8")
                assert shell_response.status == 200
            assert "Mealplan UI" in shell_html
            assert "prefers-color-scheme: dark" in shell_html

            with urllib.request.urlopen(  # noqa: S310
                f"http://{UI_HOST}:{port}/api/v1/health", timeout=2
            ) as health_response:
                health_payload = json.loads(health_response.read().decode("utf-8"))
                assert health_response.status == 200
            assert health_payload == {"status": "ok"}

            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0
            assert stderr == ""
            assert f"UI available at http://{UI_HOST}:{port}/calculate" in stdout
            assert f"Health endpoint: http://{UI_HOST}:{port}/api/v1/health" in stdout
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def test_ui_mode_fails_when_port_range_is_exhausted() -> None:
    port_start, port_end = _find_consecutive_free_ports(count=2)
    env = os.environ | {
        UI_PORT_START_ENV: str(port_start),
        UI_PORT_END_ENV: str(port_end),
    }

    with _reserve_ports(range(port_start, port_end + 1)):
        result = subprocess.run(  # noqa: S603
            _ui_command(),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    assert result.returncode != 0
    expected_error = (
        f"UI startup failed: no free port in range {port_start}..{port_end} on {UI_HOST}"
    )
    assert expected_error in result.stderr
