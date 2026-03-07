# MODEL --- `mealplan` Domain Model Specification

## 1. Purpose
This document defines the canonical domain model for `mealplan`: object structures, value domains, units, invariants, verification rules, and deterministic examples.  
`docs/ARCHITECTURE.md` references this file as the single source of truth for model-level detail.

## 2. Modeling Conventions
- Numeric quantities use SI-style units where applicable (`kg`, `g`, `minutes`).
- All calculations are deterministic and side-effect free.
- Domain values are validated before entering core calculation services.
- Meal ordering is fixed and canonical:
  1. `breakfast`
  2. `morning-snack`
  3. `lunch`
  4. `afternoon-snack`
  5. `dinner`
  6. `evening-snack`

## 3. Enumerations and Allowed Values

### 3.1 `Gender`
- Type: string enum
- Allowed values:
  - `male`
  - `female`

### 3.2 `ActivityLevel`
- Type: string enum
- Allowed values and factors:
  - `low` -> `1.2`
  - `medium` -> `1.375`
  - `high` -> `1.55`

### 3.3 `CarbMode`
- Type: string enum
- Allowed values:
  - `low`
  - `normal`
  - `periodized`

### 3.4 `TrainingLoadTomorrow`
- Type: string enum
- Allowed values:
  - `low`
  - `medium`
  - `high`

### 3.5 `MealName`
- Type: string enum
- Allowed values (fixed order):
  - `breakfast`
  - `morning-snack`
  - `lunch`
  - `afternoon-snack`
  - `dinner`
  - `evening-snack`

## 4. Scalar Value Definitions

### 4.1 Person and Activity Inputs
- `age`
  - Type: integer
  - Unit: years
  - Range: `age > 0`
- `weight_kg`
  - Type: float
  - Unit: kilograms
  - Range: `weight_kg > 0`
- `height_cm`
  - Type: integer
  - Unit: centimeters
  - Range: `height_cm > 0`
  - Upper bound: unbounded in current specification
  - Parsing policy: strict integer only (numeric strings are invalid)

### 4.2 Training Inputs
- `zones_minutes`
  - Type: mapping `zone -> minutes`
  - Zone keys: `1`, `2`, `3`, `4`, `5`
  - Minutes type: integer
  - Minutes range: `>= 0`
  - Additional rule: omit key or set `0` if no time in zone.
- `training_before_meal`
  - Type: `MealName`
  - Required iff any training minutes are supplied.

### 4.3 Computed Nutrition Values
- `tdee_kcal`
  - Type: float
  - Unit: kcal/day
  - Rule: computed from BMR * activity factor.
- `training_carbs_g`
  - Type: float
  - Unit: grams/day
  - Rule:
    - all training in zone 1 -> `0`
    - any zone >=2 -> total training minutes * `1 g/min` (equivalent to 60 g/hour)
- `protein_g`
  - Type: float
  - Unit: grams/day
  - Rule: `2 * weight_kg`
- `carbs_g`
  - Type: float
  - Unit: grams/day
  - Rule by `CarbMode`:
    - `low`: `3 * weight_kg`
    - `normal`: `5 * weight_kg`
    - `periodized`: `4 * weight_kg` baseline before redistribution
- `fat_g`
  - Type: float
  - Unit: grams/day
  - Rule:
    - `fat_kcal = total_kcal - (protein_g * 4) - (carbs_g * 4)`
    - `fat_g = fat_kcal / 9`
  - Range: `fat_g >= 0` (hard validation)

## 5. Domain Objects

### 5.1 `UserProfile`
- Fields:
  - `age: int`
  - `gender: Gender`
  - `height_cm: int`
  - `weight_kg: float`
  - `activity_level: ActivityLevel`
- Invariants:
  - `age > 0`
  - `height_cm > 0`
  - `weight_kg > 0`
  - `gender` and `activity_level` in allowed enums

### 5.2 `TrainingSession`
- Fields:
  - `zones_minutes: dict[int, int]` for zones 1-5
  - `training_before_meal: MealName | None`
- Invariants:
  - Keys must be subset of `{1,2,3,4,5}`
  - Values must be integers `>= 0`
  - If total training minutes > 0, `training_before_meal` is required

### 5.3 `MacroTargets`
- Fields:
  - `protein_g: float`
  - `carbs_g: float`
  - `fat_g: float`
- Invariants:
  - `protein_g >= 0`
  - `carbs_g >= 0`
  - `fat_g >= 0`

### 5.4 `MealAllocation`
- Fields:
  - `meal_name: MealName`
  - `protein_g: float`
  - `carbs_g: float`
  - `fat_g: float`
  - `kcal: float` (derived display field)
- Invariants:
  - `meal_name` must be unique within a plan
  - `protein_g`, `carbs_g`, `fat_g` each `>= 0`
  - `kcal` is derived from displayed meal macros (`4/4/9`), with final display-only reconciliation allowed on `evening-snack`.

### 5.5 `ResponseMealAllocation`
- Fields:
  - `meal: MealName | "training"`
  - `protein_g: float`
  - `carbs_g: float`
  - `fat_g: float`
  - `kcal: float`
- Invariants:
  - At most one `training` row may be present.
  - Canonical-order validation is applied to non-training meals only.
  - If `meal == "training"` then `protein_g = 0`, `fat_g = 0`, and `carbs_g = training_carbs_g`.

### 5.6 `MealPlan`
- Fields:
  - `tdee_kcal: float`
  - `training_carbs_g: float`
  - `macro_targets: MacroTargets`
  - `meal_allocations: list[MealAllocation]` (length exactly 6)
- Invariants:
  - Meal list includes every canonical `MealName` exactly once in canonical order
  - Sum of meal macros equals macro targets (with defined rounding policy)

## 6. Rule Objects and Service Contracts

### 6.1 Energy Rule Contract
- Input: `UserProfile`
- Output: `tdee_kcal: float`
- Formula:
  - Men: `BMR = 10*weight + 6.25*height - 5*age + 5`
  - Women: `BMR = 10*weight + 6.25*height - 5*age - 161`
  - `TDEE = BMR * activity_factor`

### 6.2 Training Demand and Fuel Rule Contract
- Training calorie demand:
  - Input: normalized `zones_minutes: Mapping[int, int]` with canonical keys `1..5`
  - Canonical API: `calculate_training_calorie_demand_kcal(zones_minutes: Mapping[int, int]) -> float`
  - Output: `training_calorie_demand_kcal: float`
  - Logic:
    - All zone minutes (including zone 1) contribute.
    - `training_calorie_demand_kcal = sum(minutes) * 4.0`

- Training fueling:
- Input: normalized `zones_minutes: Mapping[int, int]` with canonical keys `1..5`
- Canonical API: `calculate_training_carbs_g(zones_minutes: Mapping[int, int]) -> float`
- Output: `training_carbs_g: float`
- Logic:
  - If all non-zero minutes are zone 1 -> `0`
  - If any zone 2-5 has minutes > 0 -> `sum(minutes) * 1.0`
- Return semantics:
  - Always returns a `float` for valid normalized inputs.
  - Deterministic/pure: identical input mappings always produce the same output value.
- Boundary ownership:
  - Malformed training-zone payload rejection (out-of-range keys, negative minutes, non-integer minute values) is handled before domain fueling rules.
  - Domain fueling rule execution assumes Phase 3 normalization has already produced canonical zone minutes.

### 6.3 Macro Rule Contract
- Input: `UserProfile`, `CarbMode`, `tdee_kcal`
- Output: `MacroTargets`
- Logic:
  - Protein from bodyweight.
  - Carbs from selected mode.
  - Fat as residual calories.
  - Reject negative fat outcome.

### 6.4 Periodization Rule Contract
- Canonical API:
  - `calculate_periodized_carb_allocation(carb_mode: CarbMode, daily_carbs_g: float, training_before_meal: MealName | None, training_load_tomorrow: TrainingLoadTomorrow) -> dict[MealName, float]`
- Inputs:
  - `carb_mode`
  - `daily_carbs_g`
  - `training_before_meal`
  - `training_load_tomorrow`
- Output contract:
  - Returns `dict[MealName, float]`.
  - Mapping always includes all six canonical `MealName` keys in canonical order.
  - Output is deterministic for identical inputs.
- Rules:
  - Non-periodized bypass: for `CarbMode.LOW` and `CarbMode.NORMAL`, return equal split across canonical meals (`daily_carbs_g / 6.0`) with no Phase 6 rounding.
  - First two post-training meals are high-carb.
  - High-carb meal amount = `0.30 * daily_carbs` each.
  - Remaining carbs split evenly across remaining meals.
  - If tomorrow load is `high`: set `dinner` high and `evening-snack` low unless post-training rule conflicts (`training_before_meal` is `dinner` or `evening-snack`).
  - Conflict policy is explicit: preserve post-training high-meal selection and skip next-day dinner override.
  - Reconciliation check: `abs(sum_allocated_carbs - daily_carbs_g) <= 1e-9`; otherwise raise `DomainRuleError`.

### 6.5 Phase 7 Meal Assembly Contract
- Canonical API:
  - `calculate_meal_split_and_response_payload(tdee_kcal: float, training_carbs_g: float, training_calorie_demand_kcal: float, training_before_meal: MealName | None, protein_g: float, carbs_g: float, fat_g: float, carb_allocation_g_by_meal: Mapping[MealName, float]) -> dict[str, object]`
- Inputs:
  - Canonical top-level macro/energy values plus a complete six-meal carb allocation map.
- Output contract:
  - Returns top-level response fields (`TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`, `total_kcal`) plus response `meals`.
  - `meals` contains exactly six canonical entries plus at most one optional `training` entry.
  - Optional `training` entry is inserted immediately before `training_before_meal` when `training_carbs_g > 0`; no `training` entry is emitted when `training_carbs_g == 0`.
- Rules:
  - Protein and fat are split equally across six meals using float arithmetic before output-boundary rounding.
  - Carbs per meal are sourced from `carb_allocation_g_by_meal` with exact canonical key coverage (no missing/extra keys).
  - Round per-meal `carbs_g`, `protein_g`, `fat_g` to 2 decimals only at response-boundary serialization.
  - Each response meal row includes derived `kcal`.
  - Top-level values remain canonical inputs and are not recomputed from rounded meal rows.
  - `total_kcal` is computed at output boundary as `sum(meals[*].kcal)` after kcal reconciliation.
  - Apply deterministic residual adjustment only to `evening-snack` and in fixed macro order: `carbs_g`, `protein_g`, `fat_g`.
  - Non-training meals target displayed kcal sum is `TDEE + training_calorie_demand_kcal - (training_carbs_g * 4)`.
  - After macro reconciliation and row-level `kcal` derivation, apply a display-only residual adjustment to `evening-snack.kcal` so `sum(meals[*].kcal) == (TDEE + training_calorie_demand_kcal)` exactly.
  - If post-adjustment meal totals still mismatch top-level targets, raise `DomainRuleError` prefixed `meal_assembly.reconciliation`.

### 6.6 Phase 8 Application Boundary Contract
- Canonical API:
  - `MealPlanCalculationService.calculate(request: MealPlanRequest) -> MealPlanResponse`
- Boundary ownership:
  - Application layer composes validated request -> domain stages -> validated response DTO.
  - Response at the application boundary is always a `MealPlanResponse` instance (not a raw dict).
- Deterministic orchestration sequence:
  - Validation flow first (`validate_meal_plan_flow`).
  - Training-session normalization.
  - Domain stage composition in fixed order: energy -> macros -> fueling -> periodization -> assembly.
- Omitted training-session interpretation:
  - If `request.training_session is None`, canonical normalized training context is:
    - `zones_minutes = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}`
    - `training_before_meal = None`
  - This case is valid and must produce deterministic zero-training fueling (`training_carbs_g = 0.0`).

## 7. Verification Matrix

### 7.1 Input Verification
- Reject if `age <= 0`.
- Reject if `weight_kg <= 0`.
- Reject if `height_cm <= 0`.
- Reject non-integer `height_cm` values (including numeric strings).
- Reject unknown enum values.
- Reject zone keys outside `1..5`.
- Reject zone minutes `< 0`.
- Reject if training minutes provided and `training_before_meal` missing.

### 7.2 Domain Verification
- Reject if computed `fat_g < 0`.
- Reject if any meal list is missing a canonical meal name.
- Reject if any duplicate meal exists.
- Reject if carb allocation sum differs from daily carb target by more than `1e-9`.
- Reject if deterministic precedence cannot resolve conflict (this should never occur with current rule set).

### 7.3 Output Verification
- Output top-level fields are present: `TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`, `total_kcal`, `meals`.
- `meals` length is `6` or `7` (with at most one `training` row) and canonical ordering is preserved for non-training meals.
- Meal macro totals reconcile to top-level totals under configured rounding policy.
- Every meal row includes `kcal`, and displayed meal energy reconciles exactly: `sum(meals[*].kcal) == (TDEE + training_calorie_demand_kcal)`.

## 8. Units, Precision, and Rounding
- Base units:
  - Energy: `kcal`
  - Mass nutrients: `g`
  - Duration: `minutes`
- Internal precision:
  - Use float arithmetic; avoid early rounding in intermediate steps.
- Phase 6 periodization precision:
  - No rounding inside `calculate_periodized_carb_allocation`; preserve full float outputs for deterministic reconciliation checks.
- Output precision policy (recommended):
  - Phase 7 meal payloads round each meal macro field (`carbs_g`, `protein_g`, `fat_g`) to 2 decimals at boundary serialization only.
  - Per-meal `kcal` is derived from displayed macro grams after macro reconciliation.
- Reconciliation policy:
  - If boundary rounding creates drift, apply residual correction only to canonical last meal (`evening-snack`).
  - Apply residual correction in deterministic macro order: `carbs_g`, then `protein_g`, then `fat_g`.
  - After macro reconciliation, apply a display-only residual correction to `evening-snack.kcal` to enforce `sum(meals[*].kcal) == (TDEE + training_calorie_demand_kcal)`.

## 9. Example Specifications

### 9.1 Example Input Object
```json
{
  "age": 35,
  "gender": "male",
  "height_cm": 178,
  "weight_kg": 72.5,
  "activity_level": "medium",
  "carb_mode": "periodized",
  "training_load_tomorrow": "high",
  "training_session": {
    "zones_minutes": {"1": 20, "2": 40, "3": 0, "4": 0, "5": 0},
    "training_before_meal": "lunch"
  }
}
```

### 9.2 Example Derived Facts
- `protein_g = 145.0`
- `carbs_g (baseline periodized) = 290.0`
- `training_carbs_g = 60.0` because zone 2 is present for total 60 minutes.
- Post-training high meals start at `lunch`, then `afternoon-snack`.

### 9.3 Example Periodized Carb Distribution
Given `carbs_g = 290` and high meals at `lunch` + `afternoon-snack`:
- High meals:
  - `lunch = 87.0`
  - `afternoon-snack = 87.0`
- Remaining carbs: `116.0` across 4 meals => `29.0` each:
  - `breakfast = 29.0`
  - `morning-snack = 29.0`
  - `dinner = 29.0`
  - `evening-snack = 29.0`
- Sum check: `87 + 87 + 29 + 29 + 29 + 29 = 290`

## 10. Traceability
- PRD source rules: `docs/PRD.md` sections 3-10.
- Architecture context: `docs/ARCHITECTURE.md` sections 6-10 and 15.
- This file is canonical for domain object shapes, validation ranges, and enum/value definitions.
