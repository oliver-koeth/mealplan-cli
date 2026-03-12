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
- `vo2max`
  - Type: integer or null
  - Unit: `ml/kg/min`
  - Range: `10..100` inclusive when provided
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
- `training_kcal`
  - Type: float
  - Unit: kcal/day
  - Rule:
    - uses explicit `vo2max` when present, otherwise predicted VO2max
    - predicted VO2max = `79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)`
    - map `male -> sex = 0`, `female -> sex = 1`
    - zone coefficients are `z1=0.30`, `z2=0.50`, `z3=0.65`, `z4=0.80`, `z5=0.925`
    - `zone_kcal_per_min = weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)`
    - `training_kcal = sum(zone_minutes * zone_kcal_per_min for zones 1..5)`
    - emitted public value is rounded to 2 decimals
- `training_carbs_g`
  - Type: float
  - Unit: grams/day
  - Rule:
    - all training in zone 1 -> `0`
    - any zone >=2 -> total training minutes * `1 g/min` (equivalent to 60 g/hour)
  - Scope: internal fueling and optional training-meal budgeting only; not a public top-level response field.
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
- Invariants:
  - `meal_name` must be unique within a plan
  - `protein_g`, `carbs_g`, `fat_g` each `>= 0`

### 5.5 `ResponseMealAllocation`
- Fields:
  - `meal: MealName | "training"`
  - `carbs_strategy: "low" | "medium" | "high"`
  - `protein_g: float`
  - `carbs_g: float`
  - `fat_g: float`
  - `kcal: float`
- Invariants:
  - At most one `training` row may be present.
  - Canonical-order validation is applied to non-training meals only.
  - Each canonical non-training meal row has an explicit `carbs_strategy`.
  - If `meal == "training"` then `protein_g = 0`, `fat_g = 0`, and `carbs_g = training_carbs_g`.
  - If `meal == "training"` then `carbs_strategy = "high"`.

### 5.6 `MealPlan`
- Fields:
  - `tdee_kcal: float`
  - `training_kcal: float` (public training-demand metric)
  - `training_carbs_g: float` (internal fueling/training-meal value)
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
  - Input: `age`, `gender`, `weight_kg`, optional `vo2max`, and normalized `zones_minutes: Mapping[int, int]` with canonical keys `1..5`
  - Canonical API: `calculate_training_calorie_demand_kcal(age: int, gender: Gender, weight_kg: float, vo2max: int | None, zones_minutes: Mapping[int, int]) -> float`
  - Output: `training_calorie_demand_kcal: float`
  - Logic:
    - Use explicit `vo2max` when present, otherwise predict it as `79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)`.
    - Map `male -> sex = 0` and `female -> sex = 1`.
    - Zone intensity coefficients are `z1=0.30`, `z2=0.50`, `z3=0.65`, `z4=0.80`, `z5=0.925`.
    - `zone_kcal_per_min = weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)`.
    - `training_calorie_demand_kcal = sum(zone_minutes * zone_kcal_per_min for zones 1..5)`.
    - Internal precision stays unrounded; public `training_kcal` is rounded to 2 decimals at emission.

- Training fueling:
- Input: normalized `zones_minutes: Mapping[int, int]` with canonical keys `1..5`
- Canonical API: `calculate_training_carbs_g(zones_minutes: Mapping[int, int]) -> float`
- Output: internal `training_carbs_g: float`
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
  - `calculate_meal_split_and_response_payload(tdee_kcal: float, training_carbs_g: float, training_calorie_demand_kcal: float, carb_mode: CarbMode, training_before_meal: MealName | None, training_load_tomorrow: TrainingLoadTomorrow, protein_g: float, carbs_g: float, fat_g: float) -> dict[str, object]`
- Inputs:
  - Canonical top-level macro/energy values plus carb-mode and training-timing context.
- Output contract:
  - Returns top-level response fields (`TDEE`, `training_kcal`, `protein_g`, `carbs_g`, `fat_g`, `total_kcal`) plus response `meals`.
  - `meals` contains exactly six canonical entries plus at most one optional `training` entry.
  - Optional `training` entry is inserted immediately before `training_before_meal` when `training_carbs_g > 0`; no `training` entry is emitted when `training_carbs_g == 0`.
- Rules:
  - First compute `normal_meal_calorie_pool_kcal = TDEE + training_calorie_demand_kcal - (training_carbs_g * 4)`.
  - Allocate both non-training meal `kcal` budgets and initial protein targets across the six canonical meals using share units `2, 1, 2, 1, 2, 1`.
  - Assign baseline `carbs_strategy` from `carb_mode`: `normal -> medium`, `low -> low`, `periodized -> low`.
  - In `periodized` mode, apply post-training/high-load overrides to emitted meal strategies:
    - force `training_before_meal` high
    - force the next chronological canonical meal high when one exists
    - never wrap `evening-snack` to `breakfast`
    - if `training_load_tomorrow == high`, force `dinner` high
  - For each canonical non-training meal, assign protein calories first from meal protein grams, then derive remaining calories into carbs/fat using strategy calorie shares:
    - `low -> 25% carbs / 75% fat`
    - `medium -> 66.666...% carbs / 33.333...% fat`
    - `high -> 75% carbs / 25% fat`
  - If meal protein calories exceed the meal calorie budget, reduce that meal's protein until remaining calories are non-negative and record a non-fatal warning.
  - Round per-meal `carbs_g`, `protein_g`, `fat_g` to 2 decimals only at response-boundary serialization.
  - Each response meal row includes explicit `carbs_strategy` and displayed `kcal`.
  - Top-level `protein_g`, `carbs_g`, and `fat_g` are recomputed from the final emitted meal rows.
  - `total_kcal` is computed at output boundary as `sum(meals[*].kcal)` after kcal reconciliation.
  - Non-training meals target displayed kcal sum is `normal_meal_calorie_pool_kcal`.
  - After displayed row-level `kcal` assignment, total displayed day energy must satisfy `sum(meals[*].kcal) == (TDEE + training_calorie_demand_kcal)` exactly.
  - Warnings are out-of-band assembly metadata and are not added to response payload fields.

### 6.6 Phase 8 Application Boundary Contract
- Canonical API:
  - `MealPlanCalculationService.calculate(request: MealPlanRequest) -> MealPlanResponse`
- Boundary ownership:
  - Application layer composes validated request -> domain stages -> validated response DTO.
  - Response at the application boundary is always a `MealPlanResponse` instance (not a raw dict).
- Deterministic orchestration sequence:
  - Validation flow first (`validate_meal_plan_flow`).
  - Training-session normalization.
  - Domain stage composition in fixed order: energy -> macros -> fueling -> training demand -> periodization -> assembly.
- Omitted training-session interpretation:
  - If `request.training_session is None`, canonical normalized training context is:
    - `zones_minutes = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}`
    - `training_before_meal = None`
  - This case is valid and must produce deterministic zero-training fueling (`training_carbs_g = 0.0`) and emitted `training_kcal = 0.0`.

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
- Output top-level fields are present: `TDEE`, `training_kcal`, `protein_g`, `carbs_g`, `fat_g`, `total_kcal`, `meals`.
- `meals` length is `6` or `7` (with at most one `training` row) and canonical ordering is preserved for non-training meals.
- Every emitted meal row includes `carbs_strategy`.
- Meal macro totals reconcile to top-level totals because top-level `protein_g`, `carbs_g`, and `fat_g` are derived from the final emitted meal rows.
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
  - Per-meal `kcal` is a displayed budget derived from the calories-first normal-meal pool rather than re-derived from the rounded macro grams.
- Reconciliation policy:
  - Top-level `protein_g`, `carbs_g`, and `fat_g` come from the final emitted meal rows after rounding/reconciliation.
  - Apply displayed `kcal` reconciliation after the six canonical meal budgets are allocated and the optional `training` row is inserted, so `sum(meals[*].kcal) == (TDEE + training_calorie_demand_kcal)`.

## 9. Example Specifications

### 9.1 Example Input Object
```json
{
  "age": 35,
  "gender": "male",
  "height_cm": 178,
  "weight_kg": 72.5,
  "vo2max": 58,
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
- `training_kcal` is emitted at the top level from the VO2-based demand formula, rounded to 2 decimals.
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
