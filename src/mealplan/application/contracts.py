"""Application boundary contracts for placeholder probe flow."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Final, Literal, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from mealplan.domain.enums import (
    ActivityLevel,
    CarbMode,
    CarbStrategy,
    Gender,
    MealName,
    TrainingLoadTomorrow,
)
from mealplan.domain.model import CANONICAL_MEAL_ORDER

SimulatedErrorKind = Literal["validation", "domain", "config", "output", "runtime"]
TrainingZoneKey = Literal["1", "2", "3", "4", "5"]
TrainingBeforeMeal = MealName | Literal["training"]
FoodLogMeal = MealName | Literal["training"]
USERS_REGISTER_ROUTE: Final[str] = "/api/v1/users/register"
USERS_ATTACH_TOKEN_ROUTE: Final[str] = "/api/v1/users/attach-token"
USERS_EXCHANGE_TOKEN_ROUTE: Final[str] = "/api/v1/users/exchange-token"
USER_MANAGEMENT_ROUTES: Final[tuple[str, str, str]] = (
    USERS_REGISTER_ROUTE,
    USERS_ATTACH_TOKEN_ROUTE,
    USERS_EXCHANGE_TOKEN_ROUTE,
)


class AuthErrorDefault(TypedDict):
    status: int
    message: str
    retry_after_seconds: int | None


AUTH_ERROR_DEFAULTS: Final[dict[str, AuthErrorDefault]] = {
    "auth_missing_token": {
        "status": 401,
        "message": "Authorization bearer token is required.",
        "retry_after_seconds": None,
    },
    "auth_invalid_token": {
        "status": 401,
        "message": "Authorization bearer token is invalid.",
        "retry_after_seconds": None,
    },
    "auth_token_email_mismatch": {
        "status": 403,
        "message": "Bearer token does not match the requested user email.",
        "retry_after_seconds": None,
    },
    "user_already_exists": {
        "status": 409,
        "message": "A user with the requested email already exists.",
        "retry_after_seconds": None,
    },
    "auth_rate_limited": {
        "status": 429,
        "message": "Authentication rate limit exceeded. Retry later.",
        "retry_after_seconds": 60,
    },
}

CONTRACT_UNITS_POLICY: Final[dict[str, str]] = {
    "age": "years",
    "height_cm": "cm",
    "weight_kg": "kg",
    "vo2max": "ml/kg/min",
    "zones_minutes": "minutes",
    "TDEE": "kcal/day (legacy field name retained for compatibility)",
    "training_kcal": "kcal",
    "protein_g": "g",
    "carbs_g": "g",
    "fat_g": "g",
    "total_kcal": "kcal",
    "kcal": "kcal",
    "carbs": "g",
    "fat": "g",
    "protein": "g",
    "fiber": "g",
}
_DATE_KEY_FORMAT = "%Y%m%d"


class BoundaryModel(BaseModel):
    """Shared base contract for application input/output models."""

    model_config = ConfigDict(extra="forbid")


class ApiErrorDetail(BoundaryModel):
    """Canonical API error detail shape."""

    message: StrictStr
    field: StrictStr | None = None


class ApiError(BoundaryModel):
    """Canonical API error payload used in envelopes."""

    code: StrictStr
    message: StrictStr
    request_id: StrictStr
    details: list[ApiErrorDetail] | None = None


class ApiErrorEnvelope(BoundaryModel):
    """Canonical top-level API error envelope."""

    error: ApiError


class TrainingSession(BoundaryModel):
    """Canonical training-session shape for request payloads."""

    zones_minutes: dict[TrainingZoneKey, StrictInt] = Field(
        description="Training minutes per zone key ('1'..'5').",
    )
    training_before_meal: TrainingBeforeMeal | None = None


class MealPlanRequest(BoundaryModel):
    """Canonical request DTO for CLI/application parsing."""

    age: StrictInt = Field(description="Age in years.")
    gender: Gender
    height_cm: StrictInt = Field(description="Body height in centimeters.")
    weight_kg: StrictFloat = Field(description="Body weight in kilograms.")
    vo2max: StrictInt | None = Field(
        default=None,
        description="Optional VO2max in ml/kg/min.",
        ge=10,
        le=100,
    )
    activity_level: ActivityLevel
    carb_mode: CarbMode
    training_load_tomorrow: TrainingLoadTomorrow
    training_session: TrainingSession | None = None


class UserRegisterRequest(BoundaryModel):
    """Canonical request DTO for registering a new user."""

    email: StrictStr
    name: StrictStr


class UserRegisterResponse(BoundaryModel):
    """Canonical response DTO for user registration."""

    email: StrictStr
    name: StrictStr
    token: StrictStr


class UserAttachTokenRequest(BoundaryModel):
    """Canonical request DTO for attaching an existing token."""

    email: StrictStr
    token: StrictStr


class UserAttachTokenResponse(BoundaryModel):
    """Canonical response DTO for attach-token success."""

    email: StrictStr
    name: StrictStr


class UserExchangeTokenRequest(BoundaryModel):
    """Canonical request DTO for exchanging an existing token."""

    token: StrictStr


class UserExchangeTokenResponse(BoundaryModel):
    """Canonical response DTO for token exchange success."""

    token: StrictStr


class FoodLogUpsertRequest(BoundaryModel):
    """Canonical request DTO for food-log create/update operations."""

    uuid: StrictStr | None = None
    date: StrictStr
    meal: FoodLogMeal
    name: StrictStr
    kcal: StrictFloat
    carbs: StrictFloat
    fat: StrictFloat
    protein: StrictFloat
    fiber: StrictFloat
    quantity: StrictFloat = 1.0

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        return _normalize_date_key(value)


class FoodLogSearchRequest(BoundaryModel):
    """Canonical request DTO for optional-filter food-log search."""

    date: StrictStr | None = None
    name: StrictStr | None = None
    meal: FoodLogMeal | None = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_date_key(value)


class FoodLogEntry(BoundaryModel):
    """Canonical response DTO for persisted food-log entries."""

    uuid: StrictStr
    date: StrictStr
    meal: FoodLogMeal
    name: StrictStr
    kcal: StrictFloat
    carbs: StrictFloat
    fat: StrictFloat
    protein: StrictFloat
    fiber: StrictFloat

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        return _normalize_date_key(value)


class MealAllocation(BoundaryModel):
    """Canonical per-meal macro allocation in response payloads."""

    meal: MealName | Literal["training"]
    carbs_strategy: CarbStrategy
    carbs_g: StrictFloat
    protein_g: StrictFloat
    fat_g: StrictFloat
    kcal: StrictFloat


class MealPlanResponse(BoundaryModel):
    """Canonical response DTO for application/CLI output payloads."""

    TDEE: StrictFloat = Field(
        description=(
            "Legacy output field name representing total daily energy "
            "expenditure (kcal/day)."
        ),
    )
    training_kcal: StrictFloat = Field(
        description="Rounded training calorie demand for the planned day in kcal.",
    )
    protein_g: StrictFloat
    carbs_g: StrictFloat
    fat_g: StrictFloat
    total_kcal: StrictFloat = Field(
        description="Sum of displayed meal kcal values for the planned day.",
    )
    meals: list[MealAllocation]

    @model_validator(mode="after")
    def _ensure_canonical_meal_order(self) -> MealPlanResponse:
        """Require canonical order plus optional single training meal."""
        meal_sequence = [entry.meal for entry in self.meals]
        counts = Counter(meal_sequence)
        training_count = counts["training"]
        if training_count > 1:
            raise ValueError("meals may include at most one training meal")

        canonical_only_sequence = [meal for meal in meal_sequence if meal != "training"]
        if canonical_only_sequence != list(CANONICAL_MEAL_ORDER):
            raise ValueError("meals must match canonical meal order exactly")
        return self

    @model_validator(mode="after")
    def _ensure_total_kcal_matches_meal_sum(self) -> MealPlanResponse:
        displayed_total = round(sum(entry.kcal for entry in self.meals), 2)
        if round(self.total_kcal, 2) != displayed_total:
            raise ValueError("total_kcal must equal sum(meals[*].kcal)")
        return self

    @model_validator(mode="after")
    def _ensure_total_kcal_matches_tdee_plus_training(self) -> MealPlanResponse:
        expected_total = round(self.TDEE + self.training_kcal, 2)
        if round(self.total_kcal, 2) != expected_total:
            raise ValueError("total_kcal must equal TDEE + training_kcal")
        return self

    @classmethod
    def placeholder(cls) -> MealPlanResponse:
        """Build a zeroed response shape usable before calculation phases are implemented."""
        return cls(
            TDEE=0.0,
            training_kcal=0.0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
            total_kcal=0.0,
            meals=[
                MealAllocation(
                    meal=meal,
                    carbs_strategy=CarbStrategy.LOW,
                    carbs_g=0.0,
                    protein_g=0.0,
                    fat_g=0.0,
                    kcal=0.0,
                )
                for meal in CANONICAL_MEAL_ORDER
            ],
        )


class ProbeRequest(BoundaryModel):
    """Placeholder probe request payload for CLI-to-application boundary."""

    # TODO(phase-2): Extend with real user input fields for planning workflows.
    simulate_error: SimulatedErrorKind | None = Field(
        default=None,
        description="Optional named error path used only for scaffolding tests.",
    )


class ProbeResponse(BoundaryModel):
    """Placeholder probe response payload for application-to-CLI boundary."""

    # TODO(phase-2): Replace message-only shape with structured domain output.
    message: str = Field(description="Deterministic placeholder output.")


def _normalize_date_key(date_key: str) -> str:
    try:
        parsed = datetime.strptime(date_key, _DATE_KEY_FORMAT)
    except ValueError as error:
        raise ValueError("expected YYYYMMDD") from error
    canonical = parsed.strftime(_DATE_KEY_FORMAT)
    if canonical != date_key:
        raise ValueError("expected YYYYMMDD")
    return canonical
