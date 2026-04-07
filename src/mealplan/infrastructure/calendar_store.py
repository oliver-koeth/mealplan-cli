"""File-backed JSON storage for date-keyed calendar meal plans."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from mealplan.shared.errors import ConfigError, DomainRuleError, ValidationError

_DATE_KEY_FORMAT = "%Y%m%d"


class JsonCalendarStore:
    """Persist and retrieve meal plan payloads keyed by canonical YYYYMMDD dates."""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path

    def save(self, *, date_key: str, payload: Mapping[str, object]) -> None:
        """Persist payload for a date key, overwriting an existing entry if present."""
        canonical_date = _normalize_date_key(date_key)
        store = self._load_store()
        store[canonical_date] = dict(payload)
        self._write_store(store)

    def get(self, *, date_key: str) -> dict[str, Any]:
        """Return the payload for a date key or raise a deterministic not-found error."""
        canonical_date = _normalize_date_key(date_key)
        store = self._load_store()
        if canonical_date not in store:
            raise DomainRuleError(f"calendar.{canonical_date}: meal plan not found")
        stored_payload = store[canonical_date]
        if not isinstance(stored_payload, dict):
            raise ConfigError(f"calendar.{canonical_date}: persisted payload must be an object")
        return dict(stored_payload)

    def _load_store(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            self._write_store({})
            return {}
        try:
            parsed = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"calendar.store: unable to read storage file: {error}") from error
        if not isinstance(parsed, dict):
            raise ConfigError("calendar.store: storage root must be a JSON object")
        return dict(parsed)

    def _write_store(self, store: Mapping[str, object]) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                json.dumps(store, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise ConfigError(f"calendar.store: unable to write storage file: {error}") from error


def _normalize_date_key(date_key: str) -> str:
    try:
        parsed = datetime.strptime(date_key, _DATE_KEY_FORMAT)
    except ValueError as error:
        raise ValidationError("date: expected YYYYMMDD") from error
    canonical = parsed.strftime(_DATE_KEY_FORMAT)
    if canonical != date_key:
        raise ValidationError("date: expected YYYYMMDD")
    return canonical
