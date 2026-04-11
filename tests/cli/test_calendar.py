"""CLI integration tests for calendar retrieval command behavior."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mealplan.application.contracts import MealPlanResponse
from mealplan.cli.main import CALENDAR_STORE_PATH_ENV, app
from mealplan.infrastructure import (
    USERS_STORE_PATH_ENV,
    JsonCalendarStore,
    JsonUsersStore,
    user_email_to_filename_prefix,
)

runner = CliRunner()
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _required_calendar_args() -> list[str]:
    return [
        "calendar",
        "--date",
        "20260406",
    ]


def _normalized_stderr(stderr: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", stderr)


def _write_calendar_entry(*, storage_path: Path) -> MealPlanResponse:
    response = MealPlanResponse.placeholder()
    store = JsonCalendarStore(storage_path)
    store.save(date_key="20260406", payload=response.model_dump(mode="json"))
    return response


def test_calendar_command_returns_persisted_payload_in_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "calendar.json"
    expected = _write_calendar_entry(storage_path=storage_path)
    monkeypatch.setenv(CALENDAR_STORE_PATH_ENV, str(storage_path))

    result = runner.invoke(app, _required_calendar_args())

    assert result.exit_code == 0
    assert json.loads(result.stdout) == expected.model_dump(mode="json")


def test_calendar_command_reads_user_partitioned_store_when_user_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "calendar.json"
    users_path = tmp_path / "users.json"
    users_store = JsonUsersStore(users_path)
    users_store.upsert_user(
        email="alice@example.com",
        name="Alice",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )
    expected = MealPlanResponse.placeholder()
    user_prefix = user_email_to_filename_prefix("alice@example.com")
    user_calendar_path = tmp_path / f"{user_prefix}-calendar.json"
    store = JsonCalendarStore(user_calendar_path)
    store.save(date_key="20260406", payload=expected.model_dump(mode="json"))
    monkeypatch.setenv(CALENDAR_STORE_PATH_ENV, str(storage_path))
    monkeypatch.setenv(USERS_STORE_PATH_ENV, str(users_path))

    result = runner.invoke(app, [*_required_calendar_args(), "--user", "ALICE@example.com"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == expected.model_dump(mode="json")


@pytest.mark.parametrize("output_format", ["text", "table"])
def test_calendar_command_renders_supported_non_json_formats(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    output_format: str,
) -> None:
    storage_path = tmp_path / "calendar.json"
    _write_calendar_entry(storage_path=storage_path)
    monkeypatch.setenv(CALENDAR_STORE_PATH_ENV, str(storage_path))

    result = runner.invoke(
        app,
        [*_required_calendar_args(), "--format", output_format],
    )

    assert result.exit_code == 0
    assert "TDEE" in result.stdout
    assert "training_kcal" in result.stdout


def test_calendar_help_documents_date_and_format_behavior() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "calendar", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    stdout = _normalized_stderr(result.stdout)
    assert "--date" in stdout
    assert "YYYYMMDD" in stdout
    assert "--format" in stdout
    assert "json|text|table" in stdout


def test_calendar_missing_date_returns_domain_exit_code(tmp_path: Path) -> None:
    storage_path = tmp_path / "calendar.json"
    env = dict(os.environ)
    env[CALENDAR_STORE_PATH_ENV] = str(storage_path)

    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "calendar", "--date", "20260406"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 3
    assert "Error: calendar.20260406: meal plan not found" in result.stderr


def test_calendar_invalid_date_format_returns_validation_exit_code(tmp_path: Path) -> None:
    storage_path = tmp_path / "calendar.json"
    env = dict(os.environ)
    env[CALENDAR_STORE_PATH_ENV] = str(storage_path)

    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "calendar", "--date", "2026-04-06"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Error: date: expected YYYYMMDD" in result.stderr


def test_calendar_unknown_user_returns_validation_exit_code(tmp_path: Path) -> None:
    storage_path = tmp_path / "calendar.json"
    users_path = tmp_path / "users.json"
    env = dict(os.environ)
    env[CALENDAR_STORE_PATH_ENV] = str(storage_path)
    env[USERS_STORE_PATH_ENV] = str(users_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "calendar",
            "--date",
            "20260406",
            "--user",
            "missing@example.com",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Error: user: unknown user 'missing@example.com'" in result.stderr
