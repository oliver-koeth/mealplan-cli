"""Shared helpers for hybrid golden snapshot assertions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NUMERIC_TOLERANCE_ABS = 0.01
_TOLERANT_TOP_LEVEL_NUMERIC_FIELDS = frozenset(
    {"TDEE", "training_carbs_g", "protein_g", "carbs_g", "fat_g"}
)
_TOLERANT_MEAL_NUMERIC_FIELDS = frozenset({"protein_g", "carbs_g", "fat_g"})


def load_golden_json(path: Path) -> Any:
    """Load a JSON golden fixture preserving key order for strict comparisons."""
    return json.loads(path.read_text(encoding="utf-8"))


def to_canonical_json_object(payload: Any) -> Any:
    """Round-trip JSON payload with sorted keys for deterministic key ordering."""
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def assert_hybrid_snapshot_match(actual: Any, expected: Any) -> None:
    """Assert strict structure with tolerance only for approved numeric fields."""
    _assert_node(actual=actual, expected=expected, path=())


def _assert_node(*, actual: Any, expected: Any, path: tuple[str | int, ...]) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), _path_error(
            path,
            f"expected dict, got {type(actual).__name__}",
        )
        expected_keys = list(expected.keys())
        actual_keys = list(actual.keys())
        assert actual_keys == expected_keys, _path_error(
            path,
            f"dict keys/order mismatch: expected {expected_keys}, got {actual_keys}",
        )
        for key in expected_keys:
            _assert_node(actual=actual[key], expected=expected[key], path=(*path, key))
        return

    if isinstance(expected, list):
        assert isinstance(actual, list), _path_error(
            path,
            f"expected list, got {type(actual).__name__}",
        )
        assert len(actual) == len(expected), _path_error(
            path,
            f"list length mismatch: expected {len(expected)}, got {len(actual)}",
        )
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            _assert_node(actual=actual_item, expected=expected_item, path=(*path, index))
        return

    if _is_tolerant_numeric_path(path):
        assert isinstance(actual, int | float), _path_error(
            path,
            f"expected numeric value, got {type(actual).__name__}",
        )
        assert isinstance(expected, int | float), _path_error(
            path,
            f"expected numeric fixture value, got {type(expected).__name__}",
        )
        difference = abs(float(actual) - float(expected))
        assert difference <= NUMERIC_TOLERANCE_ABS, _path_error(
            path,
            "numeric mismatch "
            f"(expected {expected}, got {actual}, abs diff {difference:.6f}, "
            f"tolerance {NUMERIC_TOLERANCE_ABS})",
        )
        return

    assert type(actual) is type(expected), _path_error(
        path,
        f"type mismatch: expected {type(expected).__name__}, got {type(actual).__name__}",
    )
    assert actual == expected, _path_error(
        path,
        f"value mismatch: expected {expected!r}, got {actual!r}",
    )


def _is_tolerant_numeric_path(path: tuple[str | int, ...]) -> bool:
    if len(path) == 1 and isinstance(path[0], str):
        return path[0] in _TOLERANT_TOP_LEVEL_NUMERIC_FIELDS

    if (
        len(path) == 3
        and path[0] == "meals"
        and isinstance(path[1], int)
        and isinstance(path[2], str)
    ):
        return path[2] in _TOLERANT_MEAL_NUMERIC_FIELDS

    return False


def _path_error(path: tuple[str | int, ...], message: str) -> str:
    if not path:
        return message

    rendered_path = ".".join(str(part) for part in path)
    return f"{rendered_path}: {message}"
