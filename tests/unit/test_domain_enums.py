"""Tests for canonical domain enum contracts."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)


class EnumProbe(BaseModel):
    """Minimal model used to validate enum parsing behavior."""

    gender: Gender
    activity_level: ActivityLevel
    carb_mode: CarbMode
    training_load_tomorrow: TrainingLoadTomorrow
    meal: MealName


def test_canonical_enum_values_are_exact() -> None:
    assert [member.value for member in Gender] == ["male", "female"]
    assert [member.value for member in ActivityLevel] == ["low", "medium", "high"]
    assert [member.value for member in CarbMode] == ["low", "normal", "periodized"]
    assert [member.value for member in TrainingLoadTomorrow] == ["low", "medium", "high"]
    assert [member.value for member in MealName] == [
        "breakfast",
        "morning-snack",
        "lunch",
        "afternoon-snack",
        "dinner",
        "evening-snack",
    ]


def test_enum_probe_accepts_known_values() -> None:
    payload = {
        "gender": "male",
        "activity_level": "medium",
        "carb_mode": "periodized",
        "training_load_tomorrow": "high",
        "meal": "dinner",
    }

    parsed = EnumProbe.model_validate(payload)
    assert parsed.model_dump() == payload


def test_enum_probe_rejects_unknown_values() -> None:
    payload = {
        "gender": "unknown",
        "activity_level": "medium",
        "carb_mode": "periodized",
        "training_load_tomorrow": "high",
        "meal": "dinner",
    }

    try:
        EnumProbe.model_validate(payload)
    except ValidationError as error:
        assert error.errors()[0]["loc"] == ("gender",)
        assert error.errors()[0]["type"] == "enum"
    else:
        raise AssertionError("Expected invalid enum payload to fail.")
