"""CLI integration tests for food-log create/update command behavior."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mealplan.cli.main import FOOD_LOG_STORE_PATH_ENV, app

runner = CliRunner()
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _required_log_args() -> list[str]:
    return [
        "log",
        "--date",
        "20260408",
        "--meal",
        "lunch",
        "--name",
        "Oats",
        "--kcal",
        "380",
        "--carbs",
        "55",
        "--fat",
        "8",
        "--protein",
        "14",
        "--fiber",
        "9",
    ]


def _normalized_stderr(stderr: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", stderr)


def test_log_command_creates_entry_from_required_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))

    result = runner.invoke(app, _required_log_args())

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["date"] == "20260408"
    assert payload["meal"] == "lunch"
    assert payload["name"] == "Oats"
    assert payload["kcal"] == 380.0
    assert payload["carbs"] == 55.0
    assert payload["fat"] == 8.0
    assert payload["protein"] == 14.0
    assert payload["fiber"] == 9.0
    assert isinstance(payload["uuid"], str)
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    entry = next(iter(persisted.values()))
    assert "quantity" not in entry


def test_log_command_applies_optional_quantity_multiplier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))

    result = runner.invoke(app, [*_required_log_args(), "--quantity", "2.0"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kcal"] == 760.0
    assert payload["carbs"] == 110.0
    assert payload["fat"] == 16.0
    assert payload["protein"] == 28.0
    assert payload["fiber"] == 18.0


def test_log_command_supports_json_payload_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))

    result = runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                '{"date":"20260408","meal":"dinner","name":"Salmon",'
                '"kcal":420,"carbs":12,"fat":24,"protein":38,"fiber":0}'
            ),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["date"] == "20260408"
    assert payload["meal"] == "dinner"
    assert payload["name"] == "Salmon"
    assert payload["kcal"] == 420.0


def test_log_command_updates_existing_entry_when_json_has_uuid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))
    created = runner.invoke(app, _required_log_args())
    created_payload = json.loads(created.stdout)

    update_result = runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                "{"
                f'"uuid":"{created_payload["uuid"]}",'
                '"date":"20260408","meal":"lunch","name":"Oats",'
                '"kcal":400,"carbs":58,"fat":9,"protein":15,"fiber":10'
                "}"
            ),
        ],
    )

    assert update_result.exit_code == 0
    updated_payload = json.loads(update_result.stdout)
    assert updated_payload["uuid"] == created_payload["uuid"]
    assert updated_payload["kcal"] == 400.0
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert list(persisted.keys()) == [created_payload["uuid"]]


def test_log_command_rejects_mixing_json_and_field_flags(tmp_path: Path) -> None:
    storage_path = tmp_path / "food-log.json"
    env = dict(os.environ)
    env[FOOD_LOG_STORE_PATH_ENV] = str(storage_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "log",
            "--json",
            '{"date":"20260408","meal":"lunch","name":"Oats","kcal":380,'
            '"carbs":55,"fat":8,"protein":14,"fiber":9}',
            "--date",
            "20260408",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Error: --json cannot be combined with individual field flags" in result.stderr


def test_log_unknown_uuid_update_returns_domain_exit_code(tmp_path: Path) -> None:
    storage_path = tmp_path / "food-log.json"
    env = dict(os.environ)
    env[FOOD_LOG_STORE_PATH_ENV] = str(storage_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mealplan",
            "log",
            "--uuid",
            "00000000-0000-0000-0000-000000000001",
            "--date",
            "20260408",
            "--meal",
            "lunch",
            "--name",
            "Oats",
            "--kcal",
            "380",
            "--carbs",
            "55",
            "--fat",
            "8",
            "--protein",
            "14",
            "--fiber",
            "9",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 3
    assert "Error: log.00000000-0000-0000-0000-000000000001: entry not found" in result.stderr


def test_log_help_includes_json_payload_example() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mealplan", "log", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    stdout = _normalized_stderr(result.stdout)
    assert "--json" in stdout
    assert "mealplan log --json" in stdout


def test_log_search_returns_json_array_with_no_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))
    runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                '{"date":"20260407","meal":"breakfast","name":"Eggs",'
                '"kcal":210,"carbs":2,"fat":15,"protein":18,"fiber":0}'
            ),
        ],
    )
    runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                '{"date":"20260408","meal":"lunch","name":"Oatmeal",'
                '"kcal":320,"carbs":52,"fat":7,"protein":12,"fiber":8}'
            ),
        ],
    )

    result = runner.invoke(app, ["log", "search"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["date"] == "20260408"
    assert payload[1]["date"] == "20260407"
    assert set(payload[0]) == {
        "uuid",
        "date",
        "meal",
        "name",
        "kcal",
        "carbs",
        "fat",
        "protein",
        "fiber",
    }


def test_log_search_applies_optional_and_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "food-log.json"
    monkeypatch.setenv(FOOD_LOG_STORE_PATH_ENV, str(storage_path))
    runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                '{"date":"20260408","meal":"lunch","name":"Greek Yogurt",'
                '"kcal":180,"carbs":12,"fat":6,"protein":20,"fiber":0}'
            ),
        ],
    )
    runner.invoke(
        app,
        [
            "log",
            "--json",
            (
                '{"date":"20260408","meal":"dinner","name":"Yogurt Bowl",'
                '"kcal":260,"carbs":34,"fat":8,"protein":14,"fiber":5}'
            ),
        ],
    )

    result = runner.invoke(
        app,
        ["log", "search", "--date", "20260408", "--name", "yogurt", "--meal", "lunch"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["meal"] == "lunch"
    assert payload[0]["name"] == "Greek Yogurt"
