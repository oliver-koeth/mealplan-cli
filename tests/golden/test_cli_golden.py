"""Golden snapshot regression tests for CLI command behavior."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_GOLDEN_DIR = Path(__file__).parent / "cli"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _required_calculate_args() -> list[str]:
    return [
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
    ]


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n")


def _canonicalize_traceback(stderr: str) -> str:
    marker = "Traceback (most recent call last):\n"
    if marker not in stderr:
        return stderr

    lines = [line for line in stderr.strip("\n").split("\n") if line]
    if not lines:
        return stderr

    first_line = lines[0]
    last_line = lines[-1]
    canonical_lines = [first_line, marker.rstrip("\n"), "<TRACEBACK>", last_line]
    return "\n".join(canonical_lines) + "\n"


def _snapshot_payload(
    *,
    exit_code: int,
    stdout: str,
    stderr: str,
    canonicalize_traceback: bool = False,
) -> str:
    normalized_stdout = _normalize_text(stdout)
    normalized_stderr = _normalize_text(_ANSI_ESCAPE_RE.sub("", stderr))
    if canonicalize_traceback:
        normalized_stderr = _canonicalize_traceback(normalized_stderr)
    payload = {
        "exit_code": exit_code,
        "stderr": normalized_stderr,
        "stdout": normalized_stdout,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _assert_golden_matches(*, fixture_name: str, actual: str) -> None:
    expected = (_GOLDEN_DIR / fixture_name).read_text(encoding="utf-8")
    assert actual == expected


@pytest.mark.parametrize(
    ("fixture_name", "args"),
    [
        ("success_default_json.golden.json", _required_calculate_args()),
        ("success_text_format.golden.json", [*_required_calculate_args(), "--format", "text"]),
        ("success_table_format.golden.json", [*_required_calculate_args(), "--format", "table"]),
        (
            "failure_missing_age.golden.json",
            [
                "calculate",
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
            ],
        ),
        (
            "failure_invalid_gender_enum.golden.json",
            [
                "calculate",
                "--age",
                "40",
                "--gender",
                "invalid",
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
            ],
        ),
        (
            "failure_invalid_output_format.golden.json",
            [
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
                "xml",
            ],
        ),
        (
            "failure_invalid_training_zones_json.golden.json",
            [*_required_calculate_args(), "--training-zones", '{"1":'],
        ),
    ],
)
def test_cli_output_matches_golden_snapshots(fixture_name: str, args: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", *args],
        check=False,
        capture_output=True,
        text=True,
    )

    actual = _snapshot_payload(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    _assert_golden_matches(fixture_name=fixture_name, actual=actual)


def test_runtime_error_default_output_matches_golden(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mealplan.cli.main import main

    class FakeCalculationService:
        def calculate(self, request: object) -> object:
            _ = request
            raise RuntimeError("simulated runtime failure")

    monkeypatch.setattr("mealplan.cli.main.MealPlanCalculationService", FakeCalculationService)
    monkeypatch.setattr(sys, "argv", ["mealplan", *_required_calculate_args()])

    with pytest.raises(SystemExit) as error_info:
        main()

    captured = capsys.readouterr()
    actual = _snapshot_payload(
        exit_code=int(error_info.value.code),
        stdout=captured.out,
        stderr=captured.err,
    )
    _assert_golden_matches(fixture_name="failure_runtime_default.golden.json", actual=actual)


def test_runtime_error_debug_output_matches_golden(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mealplan.cli.main import main

    class FakeCalculationService:
        def calculate(self, request: object) -> object:
            _ = request
            raise RuntimeError("simulated runtime failure")

    monkeypatch.setattr("mealplan.cli.main.MealPlanCalculationService", FakeCalculationService)
    monkeypatch.setattr(sys, "argv", ["mealplan", *_required_calculate_args(), "--debug"])

    with pytest.raises(SystemExit) as error_info:
        main()

    captured = capsys.readouterr()
    actual = _snapshot_payload(
        exit_code=int(error_info.value.code),
        stdout=captured.out,
        stderr=captured.err,
        canonicalize_traceback=True,
    )
    _assert_golden_matches(fixture_name="failure_runtime_debug.golden.json", actual=actual)
