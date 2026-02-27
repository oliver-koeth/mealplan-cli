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
- `height_cm` (future extension)
  - Type: float
  - Unit: centimeters
  - Current status: optional/future per PRD note; not required in v0.2 flow.

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
  - `weight_kg: float`
  - `activity_level: ActivityLevel`
  - `height_cm: float | None` (future-compatible optional)
- Invariants:
  - `age > 0`
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

### 5.5 `MealPlan`
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
- Note: until `height_cm` is formalized in CLI input, implementation uses documented default behavior.

### 6.2 Training Fuel Rule Contract
- Input: `TrainingSession`
- Output: `training_carbs_g: float`
- Logic:
  - If all non-zero minutes are zone 1 -> `0`
  - If any zone 2-5 has minutes > 0 -> `sum(minutes) * 1.0`

### 6.3 Macro Rule Contract
- Input: `UserProfile`, `CarbMode`, `tdee_kcal`
- Output: `MacroTargets`
- Logic:
  - Protein from bodyweight.
  - Carbs from selected mode.
  - Fat as residual calories.
  - Reject negative fat outcome.

### 6.4 Periodization Rule Contract (for `CarbMode=periodized`)
- Inputs:
  - `carbs_g` baseline
  - `training_before_meal`
  - `training_load_tomorrow`
- Outputs:
  - `dict[MealName, carbs_g]`
- Rules:
  - First two post-training meals are high-carb.
  - High-carb meal amount = `0.30 * daily_carbs` each.
  - Remaining carbs split evenly across remaining meals.
  - If tomorrow load is `high`: set `dinner` high and `evening-snack` low unless post-training rule conflicts (`training_before_meal` is `dinner` or `evening-snack`).
  - Enforce exact total carbs after redistribution.

## 7. Verification Matrix

### 7.1 Input Verification
- Reject if `age <= 0`.
- Reject if `weight_kg <= 0`.
- Reject unknown enum values.
- Reject zone keys outside `1..5`.
- Reject zone minutes `< 0`.
- Reject if training minutes provided and `training_before_meal` missing.

### 7.2 Domain Verification
- Reject if computed `fat_g < 0`.
- Reject if any meal list is missing a canonical meal name.
- Reject if any duplicate meal exists.
- Reject if periodized carb allocation sum differs from daily carb target.
- Reject if deterministic precedence cannot resolve conflict (this should never occur with current rule set).

### 7.3 Output Verification
- Output top-level fields are present: `TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`, `meals`.
- `meals` length is exactly 6 and ordered canonically.
- Meal macro totals reconcile to top-level totals under configured rounding policy.

## 8. Units, Precision, and Rounding
- Base units:
  - Energy: `kcal`
  - Mass nutrients: `g`
  - Duration: `minutes`
- Internal precision:
  - Use float arithmetic; avoid early rounding in intermediate steps.
- Output precision policy (recommended):
  - Round to 2 decimals at render boundary only.
- Reconciliation policy:
  - Apply deterministic residual adjustment to last meal in canonical order when rounding creates a sum drift.

## 9. Example Specifications

### 9.1 Example Input Object
```json
{
  "age": 35,
  "gender": "male",
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
