"""Verify wheel installability and post-install CLI smoke commands."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dist"
EXPECTED_TOP_LEVEL_KEYS = {
    "TDEE",
    "training_kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "total_kcal",
    "meals",
}
UI_HOST = "127.0.0.1"
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"


def _find_wheel() -> Path:
    wheels = sorted(DIST_DIR.glob("*.whl"))
    if len(wheels) != 1:
        raise AssertionError(
            f"Expected exactly one wheel in dist/, found {len(wheels)}. "
            "Run `uv run python scripts/checks/verify_package_artifacts.py` first."
        )
    return wheels[0]


def _venv_executable(venv_path: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv_path / "Scripts" / f"{name}.exe"
    return venv_path / "bin" / name


def _run_checked(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "Command failed:\n"
            f"  command: {' '.join(command)}\n"
            f"  exit_code: {result.returncode}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}\n"
        )
    return result


def _assert_help_command(command: list[str], cwd: Path) -> None:
    result = _run_checked(command, cwd=cwd)
    if "Usage" not in result.stdout:
        raise AssertionError(f"Expected help output to include `Usage`: {' '.join(command)}")


def _assert_post_install_smoke(command: list[str], cwd: Path) -> None:
    result = _run_checked(command, cwd=cwd)
    payload = json.loads(result.stdout)
    if not EXPECTED_TOP_LEVEL_KEYS.issubset(payload.keys()):
        raise AssertionError(
            "Smoke command JSON output is missing expected keys. "
            f"Expected subset: {sorted(EXPECTED_TOP_LEVEL_KEYS)}"
        )


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


def _discover_live_ui_port(*, port_start: int, port_end: int, timeout: float = 8.0) -> int:
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
    raise AssertionError("Installed wheel UI mode did not become reachable in time")


def _assert_installed_ui_mode(mealplan_executable: Path, cwd: Path) -> None:
    port_start, port_end = _find_consecutive_free_ports(count=2)
    env = os.environ | {
        "PYTHONUNBUFFERED": "1",
        UI_PORT_START_ENV: str(port_start),
        UI_PORT_END_ENV: str(port_end),
    }
    process = subprocess.Popen(  # noqa: S603
        [str(mealplan_executable), "--ui"],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        ui_port = _discover_live_ui_port(port_start=port_start, port_end=port_end)

        with urllib.request.urlopen(  # noqa: S310
            f"http://{UI_HOST}:{ui_port}/calculate", timeout=2
        ) as calculate_shell:
            html = calculate_shell.read().decode("utf-8")
            if calculate_shell.status != 200 or "Mealplan UI" not in html:
                raise AssertionError("Installed UI shell did not render expected content.")

        with urllib.request.urlopen(  # noqa: S310
            f"http://{UI_HOST}:{ui_port}/api/v1/health", timeout=2
        ) as health_response:
            payload = json.loads(health_response.read().decode("utf-8"))
            if health_response.status != 200 or payload != {"status": "ok"}:
                raise AssertionError("Installed UI health endpoint returned unexpected response.")

        request = urllib.request.Request(  # noqa: S310
            url=f"http://{UI_HOST}:{ui_port}/api/v1/calculate",
            data=json.dumps(
                {
                    "age": 40,
                    "gender": "male",
                    "height_cm": 180,
                    "weight_kg": 75.0,
                    "activity_level": "medium",
                    "carb_mode": "periodized",
                    "training_load_tomorrow": "high",
                    "training_session": {
                        "zones_minutes": {"1": 20, "2": 40, "3": 0, "4": 0, "5": 0},
                        "training_before_meal": "lunch",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as calculate_response:  # noqa: S310
            payload = json.loads(calculate_response.read().decode("utf-8"))
        if not EXPECTED_TOP_LEVEL_KEYS.issubset(payload.keys()):
            raise AssertionError(
                "Installed UI calculate endpoint returned unexpected payload keys."
            )
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            raise AssertionError(
                "Installed UI mode did not exit cleanly after terminate().\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}\n"
            )


def main() -> None:
    wheel_path = _find_wheel()

    with tempfile.TemporaryDirectory(prefix="mealplan-install-smoke-") as tmp_dir:
        temp_root = Path(tmp_dir)
        venv_path = temp_root / ".venv"

        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        pip_executable = _venv_executable(venv_path, "pip")
        python_executable = _venv_executable(venv_path, "python")
        mealplan_executable = _venv_executable(venv_path, "mealplan")

        _run_checked([str(pip_executable), "install", str(wheel_path)], cwd=temp_root)
        _assert_help_command([str(mealplan_executable), "--help"], cwd=temp_root)
        _assert_help_command(
            [str(python_executable), "-m", "mealplan", "--help"],
            cwd=temp_root,
        )
        _assert_post_install_smoke(
            [
                str(mealplan_executable),
                "calculate",
                "--date",
                "20260406",
                "--age",
                "40",
                "--gender",
                "male",
                "--height",
                "180",
                "--weight",
                "75",
                "--activity",
                "medium",
                "--carbs",
                "low",
                "--training-tomorrow",
                "high",
                "--format",
                "json",
            ],
            cwd=temp_root,
        )
        _assert_installed_ui_mode(mealplan_executable, cwd=temp_root)

    print(f"Verified install workflow from wheel: {wheel_path.name}")


if __name__ == "__main__":
    main()
