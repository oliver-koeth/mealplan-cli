"""Unit tests for file-backed calendar persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mealplan.infrastructure import JsonCalendarStore
from mealplan.shared.errors import ConfigError, DomainRuleError, ValidationError


def _store_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "calendar.json"


def test_save_creates_missing_store_file(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonCalendarStore(storage_path)

    store.save(date_key="20260406", payload={"TDEE": 2400.0, "meals": []})

    assert storage_path.exists()
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert persisted == {"20260406": {"TDEE": 2400.0, "meals": []}}


def test_save_overwrites_existing_date_payload(tmp_path: Path) -> None:
    store = JsonCalendarStore(_store_path(tmp_path))
    store.save(date_key="20260406", payload={"version": 1})

    store.save(date_key="20260406", payload={"version": 2, "meals": ["breakfast"]})

    payload = store.get(date_key="20260406")
    assert payload == {"version": 2, "meals": ["breakfast"]}


def test_get_missing_date_raises_domain_not_found_error(tmp_path: Path) -> None:
    store = JsonCalendarStore(_store_path(tmp_path))
    store.save(date_key="20260406", payload={"present": True})

    with pytest.raises(DomainRuleError, match="calendar.20260407: meal plan not found"):
        store.get(date_key="20260407")


@pytest.mark.parametrize(
    "invalid_date",
    ["2026-04-06", "2026046", "abc", "20260230", "20261301"],
)
def test_invalid_date_key_rejected_for_save_and_get(tmp_path: Path, invalid_date: str) -> None:
    store = JsonCalendarStore(_store_path(tmp_path))

    with pytest.raises(ValidationError, match="date: expected YYYYMMDD"):
        store.save(date_key=invalid_date, payload={})
    with pytest.raises(ValidationError, match="date: expected YYYYMMDD"):
        store.get(date_key=invalid_date)


def test_non_object_store_root_raises_config_error(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text("[]", encoding="utf-8")
    store = JsonCalendarStore(storage_path)

    with pytest.raises(ConfigError, match="calendar.store: storage root must be a JSON object"):
        store.get(date_key="20260406")
