"""File-backed JSON storage for UUID-keyed food-log entries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from mealplan.application.contracts import (
    FoodLogEntry,
    FoodLogSearchRequest,
    FoodLogUpsertRequest,
)
from mealplan.shared.errors import ConfigError, DomainRuleError, ValidationError

MAX_SEARCH_RESULTS = 25


class JsonFoodLogStore:
    """Persist and update food-log entries under backend-managed UUID keys."""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path

    def create(self, *, request: FoodLogUpsertRequest) -> FoodLogEntry:
        """Create a new persisted entry with a generated UUID."""
        if request.uuid is not None:
            raise ValidationError("uuid: must be omitted for create")

        entry_uuid = str(uuid4())
        entry = self._entry_from_request(request=request, entry_uuid=entry_uuid)
        store = self._load_store()
        store[entry_uuid] = entry.model_dump(mode="json")
        self._write_store(store)
        return entry

    def update(self, *, request: FoodLogUpsertRequest) -> FoodLogEntry:
        """Update an existing entry identified by UUID."""
        if request.uuid is None:
            raise ValidationError("uuid: required for update")

        store = self._load_store()
        entry_uuid = request.uuid
        if entry_uuid not in store:
            raise DomainRuleError(f"log.{entry_uuid}: entry not found")

        entry = self._entry_from_request(request=request, entry_uuid=entry_uuid)
        store[entry_uuid] = entry.model_dump(mode="json")
        self._write_store(store)
        return entry

    def search(self, *, request: FoodLogSearchRequest) -> list[FoodLogEntry]:
        """Search persisted log entries using optional-AND filter semantics."""
        store = self._load_store()
        entries: list[FoodLogEntry] = []
        for entry_uuid, payload in store.items():
            if not isinstance(payload, dict):
                raise ConfigError(f"log.{entry_uuid}: persisted payload must be an object")
            entry = FoodLogEntry.model_validate(payload)
            if request.date is not None and entry.date != request.date:
                continue
            if request.meal is not None and entry.meal != request.meal:
                continue
            if request.name is not None and request.name.lower() not in entry.name.lower():
                continue
            entries.append(entry)

        ordered = sorted(entries, key=lambda entry: (entry.date, entry.uuid), reverse=True)
        return ordered[:MAX_SEARCH_RESULTS]

    def _entry_from_request(
        self,
        *,
        request: FoodLogUpsertRequest,
        entry_uuid: str,
    ) -> FoodLogEntry:
        quantity = request.quantity
        return FoodLogEntry(
            uuid=entry_uuid,
            date=request.date,
            meal=request.meal,
            name=request.name,
            kcal=request.kcal * quantity,
            carbs=request.carbs * quantity,
            fat=request.fat * quantity,
            protein=request.protein * quantity,
            fiber=request.fiber * quantity,
        )

    def _load_store(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            self._write_store({})
            return {}
        try:
            parsed = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"log.store: unable to read storage file: {error}") from error
        if not isinstance(parsed, dict):
            raise ConfigError("log.store: storage root must be a JSON object")
        return dict(parsed)

    def _write_store(self, store: Mapping[str, object]) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                json.dumps(store, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise ConfigError(f"log.store: unable to write storage file: {error}") from error
