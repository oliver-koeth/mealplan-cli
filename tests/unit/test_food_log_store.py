"""Unit tests for file-backed food-log persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mealplan.application.contracts import FoodLogSearchRequest, FoodLogUpsertRequest
from mealplan.infrastructure import JsonFoodLogStore
from mealplan.shared.errors import ConfigError, DomainRuleError, ValidationError


def _store_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "food-log.json"


def test_create_generates_uuid_and_creates_missing_store_file(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonFoodLogStore(storage_path)
    request = FoodLogUpsertRequest.model_validate(
        {
            "date": "20260408",
            "meal": "lunch",
            "name": "Greek yogurt",
            "kcal": 140.0,
            "carbs": 8.0,
            "fat": 4.0,
            "protein": 18.0,
            "fiber": 0.0,
        }
    )

    created = store.create(request=request)

    assert created.uuid
    assert storage_path.exists()
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert list(persisted.keys()) == [created.uuid]
    assert persisted[created.uuid] == created.model_dump(mode="json")
    assert "quantity" not in persisted[created.uuid]


def test_update_replaces_existing_entry_by_uuid(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    created = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "breakfast",
                "name": "Oats",
                "kcal": 200.0,
                "carbs": 35.0,
                "fat": 5.0,
                "protein": 8.0,
                "fiber": 5.0,
            }
        )
    )

    updated = store.update(
        request=FoodLogUpsertRequest.model_validate(
            {
                "uuid": created.uuid,
                "date": "20260408",
                "meal": "breakfast",
                "name": "Oats + milk",
                "kcal": 250.0,
                "carbs": 40.0,
                "fat": 7.0,
                "protein": 11.0,
                "fiber": 6.0,
            }
        )
    )

    assert updated.uuid == created.uuid
    persisted = json.loads(_store_path(tmp_path).read_text(encoding="utf-8"))
    assert persisted[created.uuid]["name"] == "Oats + milk"
    assert persisted[created.uuid] == updated.model_dump(mode="json")


def test_update_unknown_uuid_raises_domain_not_found_error(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    request = FoodLogUpsertRequest.model_validate(
        {
            "uuid": "missing-uuid",
            "date": "20260408",
            "meal": "dinner",
            "name": "Salmon",
            "kcal": 420.0,
            "carbs": 0.0,
            "fat": 25.0,
            "protein": 35.0,
            "fiber": 0.0,
        }
    )

    with pytest.raises(DomainRuleError, match="log.missing-uuid: entry not found"):
        store.update(request=request)


def test_quantity_multiplies_nutrition_fields_and_is_not_persisted(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonFoodLogStore(storage_path)
    request = FoodLogUpsertRequest.model_validate(
        {
            "date": "20260408",
            "meal": "afternoon-snack",
            "name": "Protein shake",
            "kcal": 120.0,
            "carbs": 4.0,
            "fat": 2.0,
            "protein": 24.0,
            "fiber": 1.0,
            "quantity": 1.5,
        }
    )

    created = store.create(request=request)

    assert created.kcal == pytest.approx(180.0)
    assert created.carbs == pytest.approx(6.0)
    assert created.fat == pytest.approx(3.0)
    assert created.protein == pytest.approx(36.0)
    assert created.fiber == pytest.approx(1.5)
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert "quantity" not in persisted[created.uuid]


def test_update_applies_quantity_multiplier_and_is_not_persisted(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonFoodLogStore(storage_path)
    created = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "lunch",
                "name": "Rice bowl",
                "kcal": 500.0,
                "carbs": 70.0,
                "fat": 10.0,
                "protein": 20.0,
                "fiber": 4.0,
            }
        )
    )

    updated = store.update(
        request=FoodLogUpsertRequest.model_validate(
            {
                "uuid": created.uuid,
                "date": "20260408",
                "meal": "lunch",
                "name": "Rice bowl",
                "kcal": 500.0,
                "carbs": 70.0,
                "fat": 10.0,
                "protein": 20.0,
                "fiber": 4.0,
                "quantity": 0.5,
            }
        )
    )

    assert updated.kcal == pytest.approx(250.0)
    assert updated.carbs == pytest.approx(35.0)
    assert updated.fat == pytest.approx(5.0)
    assert updated.protein == pytest.approx(10.0)
    assert updated.fiber == pytest.approx(2.0)
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert "quantity" not in persisted[created.uuid]


def test_create_with_uuid_and_update_without_uuid_raise_validation_error(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    create_with_uuid = FoodLogUpsertRequest.model_validate(
        {
            "uuid": "manually-provided",
            "date": "20260408",
            "meal": "lunch",
            "name": "Rice bowl",
            "kcal": 500.0,
            "carbs": 70.0,
            "fat": 10.0,
            "protein": 20.0,
            "fiber": 4.0,
        }
    )
    update_without_uuid = FoodLogUpsertRequest.model_validate(
        {
            "date": "20260408",
            "meal": "lunch",
            "name": "Rice bowl",
            "kcal": 500.0,
            "carbs": 70.0,
            "fat": 10.0,
            "protein": 20.0,
            "fiber": 4.0,
        }
    )

    with pytest.raises(ValidationError, match="uuid: must be omitted for create"):
        store.create(request=create_with_uuid)
    with pytest.raises(ValidationError, match="uuid: required for update"):
        store.update(request=update_without_uuid)


def test_non_object_store_root_raises_config_error(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text("[]", encoding="utf-8")
    store = JsonFoodLogStore(storage_path)
    request = FoodLogUpsertRequest.model_validate(
        {
            "date": "20260408",
            "meal": "lunch",
            "name": "Greek yogurt",
            "kcal": 140.0,
            "carbs": 8.0,
            "fat": 4.0,
            "protein": 18.0,
            "fiber": 0.0,
        }
    )

    with pytest.raises(ConfigError, match="log.store: storage root must be a JSON object"):
        store.create(request=request)


def test_search_non_object_entry_payload_raises_config_error(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text('{"bad-entry": []}\n', encoding="utf-8")
    store = JsonFoodLogStore(storage_path)

    with pytest.raises(
        ConfigError,
        match="log.bad-entry: persisted payload must be an object",
    ):
        store.search(request=FoodLogSearchRequest.model_validate({}))


def test_search_supports_optional_and_filters_with_case_insensitive_name(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    entry_a = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "breakfast",
                "name": "Greek Yogurt",
                "kcal": 140.0,
                "carbs": 8.0,
                "fat": 4.0,
                "protein": 18.0,
                "fiber": 0.0,
            }
        )
    )
    store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "lunch",
                "name": "Chicken Bowl",
                "kcal": 500.0,
                "carbs": 50.0,
                "fat": 15.0,
                "protein": 35.0,
                "fiber": 4.0,
            }
        )
    )
    store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260407",
                "meal": "breakfast",
                "name": "yogurt parfait",
                "kcal": 260.0,
                "carbs": 32.0,
                "fat": 8.0,
                "protein": 14.0,
                "fiber": 5.0,
            }
        )
    )

    matches = store.search(
        request=FoodLogSearchRequest.model_validate(
            {"date": "20260408", "meal": "breakfast", "name": "YOG"}
        )
    )

    assert [entry.uuid for entry in matches] == [entry_a.uuid]


@pytest.mark.parametrize(
    ("filters", "expected_count"),
    [
        ({"date": "20260408"}, 2),
        ({"name": "yog"}, 2),
        ({"meal": "breakfast"}, 2),
    ],
)
def test_search_works_with_single_filter_inputs(
    tmp_path: Path,
    filters: dict[str, str],
    expected_count: int,
) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "breakfast",
                "name": "Greek Yogurt",
                "kcal": 140.0,
                "carbs": 8.0,
                "fat": 4.0,
                "protein": 18.0,
                "fiber": 0.0,
            }
        )
    )
    store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "lunch",
                "name": "Chicken Bowl",
                "kcal": 500.0,
                "carbs": 50.0,
                "fat": 15.0,
                "protein": 35.0,
                "fiber": 4.0,
            }
        )
    )
    store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260407",
                "meal": "breakfast",
                "name": "Yogurt Parfait",
                "kcal": 260.0,
                "carbs": 32.0,
                "fat": 8.0,
                "protein": 14.0,
                "fiber": 5.0,
            }
        )
    )

    matches = store.search(request=FoodLogSearchRequest.model_validate(filters))

    assert len(matches) == expected_count


def test_search_orders_results_newest_first(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    newest = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260409",
                "meal": "lunch",
                "name": "Meal C",
                "kcal": 300.0,
                "carbs": 30.0,
                "fat": 10.0,
                "protein": 20.0,
                "fiber": 4.0,
            }
        )
    )
    middle = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "lunch",
                "name": "Meal B",
                "kcal": 300.0,
                "carbs": 30.0,
                "fat": 10.0,
                "protein": 20.0,
                "fiber": 4.0,
            }
        )
    )
    oldest = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260407",
                "meal": "lunch",
                "name": "Meal A",
                "kcal": 300.0,
                "carbs": 30.0,
                "fat": 10.0,
                "protein": 20.0,
                "fiber": 4.0,
            }
        )
    )

    matches = store.search(request=FoodLogSearchRequest.model_validate({}))

    assert [entry.uuid for entry in matches] == [newest.uuid, middle.uuid, oldest.uuid]


def test_search_returns_canonical_food_log_entries(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    created = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "dinner",
                "name": "Salmon",
                "kcal": 420.0,
                "carbs": 0.0,
                "fat": 25.0,
                "protein": 35.0,
                "fiber": 0.0,
            }
        )
    )

    matches = store.search(request=FoodLogSearchRequest.model_validate({}))

    assert matches == [created]


def test_search_accepts_training_meal_entries(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    created = store.create(
        request=FoodLogUpsertRequest.model_validate(
            {
                "date": "20260408",
                "meal": "training",
                "name": "Gel",
                "kcal": 120.0,
                "carbs": 30.0,
                "fat": 0.0,
                "protein": 0.0,
                "fiber": 0.0,
            }
        )
    )

    matches = store.search(request=FoodLogSearchRequest.model_validate({"meal": "training"}))

    assert len(matches) == 1
    assert matches[0].uuid == created.uuid


def test_search_returns_latest_25_matches_only(tmp_path: Path) -> None:
    store = JsonFoodLogStore(_store_path(tmp_path))
    for index in range(30):
        day = index + 1
        store.create(
            request=FoodLogUpsertRequest.model_validate(
                {
                    "date": f"202604{day:02d}",
                    "meal": "lunch",
                    "name": f"Meal {day}",
                    "kcal": 300.0 + day,
                    "carbs": 30.0,
                    "fat": 10.0,
                    "protein": 20.0,
                    "fiber": 4.0,
                }
            )
        )

    matches = store.search(request=FoodLogSearchRequest.model_validate({}))

    assert len(matches) == 25
    assert matches[0].date == "20260430"
    assert matches[-1].date == "20260406"
