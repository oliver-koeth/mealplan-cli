"""Verify wheel installability and post-install CLI smoke commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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

    print(f"Verified install workflow from wheel: {wheel_path.name}")


if __name__ == "__main__":
    main()
