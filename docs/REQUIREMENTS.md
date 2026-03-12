# PRD --- CLI Meal Planning Tool: `mealplan`

*(Agentic / Ralph-like Coding Workflow Compatible)*

------------------------------------------------------------------------

## 1. Document Metadata

-   **Project Name:** mealplan
-   **CLI Command Name:** mealplan
-   **Version:** 0.2.0
-   **Status:** Draft
-   **Target Python Version:** 3.11+
-   **OS Targets:** Cross-platform (Linux, macOS, Windows)
-   **Packaging:** pip-installable package

------------------------------------------------------------------------

## 2. Problem Statement

Provide a deterministic CLI tool that calculates:

-   Daily caloric needs (TDEE)
-   Training fuel requirements
-   Absolute macronutrient targets
-   Distribution into 6 meals per day
-   Carb periodization based on training timing and next-day load

The tool must be fully machine-executable without ambiguity.

------------------------------------------------------------------------

## 3. Inputs

### Required Parameters

  Parameter               Type    Description
  ----------------------- ------- ---------------------------
  `--age`                 int     Age in years
  `--gender`              enum    male / female
  `--height`              int     Height in cm
  `--weight`              float   Body weight in kg
  `--activity`            enum    low / medium / high
  `--carbs`               enum    low / normal / periodized
  `--training-tomorrow`   enum    low / medium / high

### Training Today (Optional)

  ------------------------------------------------------------------------
  Parameter                    Type           Description
  ---------------------------- -------------- ----------------------------
  `--training-zones`           JSON           Minutes per zone 1--5

  `--training-before`          string         breakfast / morning-snack /
                                              lunch / afternoon-snack /
                                              dinner / evening-snack /
                                              training (parseable but
                                              semantically invalid)

  `--vo2max`                   int            Optional explicit VO2max in
                                              ml/kg/min (`10..100`
                                              inclusive)
  ------------------------------------------------------------------------

### Runtime and Output Controls

  Parameter      Type    Description
  -------------- ------- -----------------------------------------------
  `--format`     enum    json / text / table (default: json)
  `--debug`      flag    Enables traceback output on errors (stderr only)

------------------------------------------------------------------------

## 4. Energy Calculation

### 4.1 Basal Metabolic Rate (Mifflin-St Jeor)

Men: BMR = 10 × weight + 6.25 × height − 5 × age + 5

Women: BMR = 10 × weight + 6.25 × height − 5 × age − 161

Height is a required CLI input (`--height`) in centimeters.
No upper bound is defined for height in this specification.

### 4.2 Activity Multipliers

  Activity   Factor
  ---------- --------
  low        1.2
  medium     1.375
  high       1.55

TDEE = BMR × activity_factor

------------------------------------------------------------------------

## 5. Training Demand and Fueling

### 5.1 Training Calorie Demand

-   Training calorie demand is derived from a zone-weighted VO2 estimate.
-   Use explicit `--vo2max` when provided; otherwise predict VO2max as:

    `79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)`

-   Map `male -> sex = 0` and `female -> sex = 1`.
-   Use fixed zone intensity coefficients:
    `z1=0.30`, `z2=0.50`, `z3=0.65`, `z4=0.80`, `z5=0.925`.
-   Per-zone calorie demand is:

    `zone_kcal_per_min = weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)`

-   Total training demand is:

    `training_kcal = sum(zone_minutes * zone_kcal_per_min for zones 1..5)`

-   Keep full floating-point precision internally and round only emitted public
    `training_kcal` fields to 2 decimals.

### 5.2 Training Fueling

-   If ALL training is Z1 → 0g carbs
-   If ANY zone ≥ Z2 → 60g carbs per hour

training_carbs_g = duration_minutes × (60 / 60)

training_calorie_supply_kcal = training_carbs_g × 4

Fueling carbs are separate from meal carb allocations.

Phase 5 boundary note: fueling rules consume normalized zone minutes only (canonical zones `1..5` with integer minute values). Malformed input rejection is handled earlier in Phase 3 validation/normalization.

------------------------------------------------------------------------

## 6. Macronutrient Rules (Absolute Targets)

### 6.1 Protein (Fixed)

Protein = 2g × bodyweight (kg)

------------------------------------------------------------------------

### 6.2 Carbohydrate Modes (Absolute)

  Mode         Carb Target
  ------------ --------------------------------
  low          3g/kg
  normal       5g/kg
  periodized   4g/kg baseline (redistributed)

------------------------------------------------------------------------

### 6.3 Fat

fat_calories = total_calories − protein_calories − carb_calories

fat_g = fat_calories / 9

Fat must not be negative.

------------------------------------------------------------------------

## 7. Meal Structure

1.  breakfast
2.  morning-snack
3.  lunch
4.  afternoon-snack
5.  dinner
6.  evening-snack

------------------------------------------------------------------------

## 8. Periodized Carb Logic

Only applies if `--carbs periodized`.

### 8.1 Determine Post-Training Meals

Training is specified as:

`--training-before <meal>`

The specified meal is the first post-training meal.

The second post-training meal is the next chronological meal.

`--training-before=training` is syntactically accepted at input parsing, but must fail deterministic semantic runtime validation to prevent recursive insertion semantics.

------------------------------------------------------------------------

### 8.2 Post-Training Rule

-   First two post-training meals = HIGH CARB
-   Remaining meals = LOW CARB

------------------------------------------------------------------------

### 8.3 High / Low Definition (Absolute)

HIGH meal: - 30% of total daily carbs allocated to each high meal

LOW meals: - Remaining carbs distributed evenly across remaining meals

Total must equal daily carb target.

------------------------------------------------------------------------

### 8.4 Next-Day High Training Override

If:

training_tomorrow == high

Then:

-   Dinner = HIGH CARB
-   Evening-snack = LOW CARB

Exception:

If training-before dinner or evening-snack, the two-meal post-training
rule overrides.

------------------------------------------------------------------------

### 8.5 Precedence Order

1.  If not periodized → deterministic equal split across all 6 canonical meals (`daily_carbs_g / 6.0`)
2.  Apply post-training high rule
3.  Apply next-day override unless conflict
4.  Ensure carb totals reconcile to target using tolerance check (`abs(sum_allocated - daily_carbs_g) <= 1e-9`)

Phase 6 contract clarification:

-   Canonical domain API is `calculate_periodized_carb_allocation(carb_mode, daily_carbs_g, training_before_meal, training_load_tomorrow) -> dict[MealName, float]`.
-   Output is always keyed by all six canonical meals in canonical order.
-   If `training_before_meal` is `dinner` or `evening-snack`, keep post-training high-meal selection and skip next-day dinner override.

------------------------------------------------------------------------

## 9. Output Format

JSON structure:

{ "TDEE": number, "training_kcal": number, "protein_g": number,
"carbs_g": number, "fat_g": number, "total_kcal": number, "meals": \[
{"meal":"breakfast","carbs_g":x,"protein_g":y,"fat_g":z,"kcal":k} \] }

### 9.1 Phase 7 Assembly and Rounding Contract

-   Canonical meal-assembly API is domain-only:
    `calculate_meal_split_and_response_payload(tdee_kcal, training_carbs_g, training_calorie_demand_kcal, carb_mode, training_before_meal, training_load_tomorrow, protein_g, carbs_g, fat_g)`.
-   The six canonical non-training meals are budgeted from a calories-first pool:
    `normal_meal_calorie_pool_kcal = TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`.
-   `training_calorie_supply_kcal` remains `training_carbs_g * 4`.
-   `training_carbs_g` is an internal fueling and training-meal input only; the
    public top-level response field is `training_kcal`.
-   Distribute both normal-meal `kcal` budgets and initial protein targets across
    `breakfast`, `morning-snack`, `lunch`, `afternoon-snack`, `dinner`, `evening-snack`
    with canonical shares `2/9, 1/9, 2/9, 1/9, 2/9, 1/9`.
-   Each canonical meal row includes `carbs_strategy` with one of `low`, `medium`, or `high`.
-   Strategy assignment rules:
    - `--carbs normal` -> all six canonical meals use `medium`
    - `--carbs low` -> all six canonical meals use `low`
    - `--carbs periodized` -> baseline all six canonical meals to `low`, then apply post-training overrides
-   Periodized override rules in meal assembly:
    - mark `--training-before` meal as the first high-carb meal
    - mark the next chronological canonical meal as the second high-carb meal
    - do not wrap from `evening-snack` to `breakfast`
    - if `--training-before=dinner`, only `dinner` is forced high unless tomorrow-load rule overrides
    - if `--training-before=evening-snack`, only `evening-snack` is forced high unless tomorrow-load rule overrides
    - if `--training-tomorrow=high`, force `dinner` to `high` in periodized mode
-   For each canonical non-training meal, assign protein calories first, then derive remaining calories into carbs and fat by strategy:
    - `low`: `1/4` of remaining calories to carbs, `3/4` to fat
    - `medium`: `2/3` of remaining calories to carbs, `1/3` to fat
    - `high`: `3/4` of remaining calories to carbs, `1/4` to fat
-   If a meal's assigned protein calories exceed its calorie budget, reduce protein for that meal until remaining calories are non-negative and emit a warning to stderr on otherwise successful runs.
-   Do not add warning fields to JSON, text, or table payloads.
-   Response `meals` must include the six canonical entries in canonical order, with at most one optional `training` entry.
-   If `training_carbs_g > 0`, insert exactly one `training` meal before `training_before_meal` (append only when no target exists); if `training_carbs_g == 0`, insert none.
-   Training meal composition is carbs-only with `carbs_strategy=high`: `carbs_g = training_carbs_g`, `protein_g = 0`, `fat_g = 0`.
-   Per-meal `carbs_g`, `protein_g`, and `fat_g` values are rounded to 2 decimals at output boundary only, and each meal row includes displayed `kcal`.
-   Top-level `protein_g`, `carbs_g`, and `fat_g` are derived from the final emitted meal rows.
-   Top-level `total_kcal` is output-only and equals the sum of displayed meal `kcal` values.
-   Top-level `training_kcal` is the public training-demand metric; internal
    `training_carbs_g` remains part of fueling and optional training-meal
    assembly only.
-   After canonical meal `kcal` budgets are allocated, apply display-only `kcal` reconciliation so:
    `sum(meals[*].kcal) == (TDEE + training_kcal)`.

### 9.2 Phase 8 Application Orchestration Flow

-   Canonical application orchestration API is:
    `MealPlanCalculationService.calculate(request: MealPlanRequest) -> MealPlanResponse`.
-   The orchestration flow is validation-first and deterministic:
    1. `validate_meal_plan_flow` (schema + semantic + invariant gate)
    2. training-session normalization
    3. energy calculation
    4. macro target calculation
    5. training fueling calculation for internal `training_carbs_g`
    6. training calorie demand calculation for public `training_kcal`
    7. meal assembly and `MealPlanResponse` model validation
-   Standalone periodization allocation remains available as a pure domain helper, but calories-first response assembly is now the canonical source for emitted meal strategies and meal-level carb/fat allocation.
-   `training_session` is optional at the request boundary.
-   If `training_session` is omitted (`null`/`None`), orchestration must treat it as zero training with canonical defaults:
    - `zones_minutes = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}`
    - `training_before_meal = null`
-   For omitted training sessions, calculation proceeds normally with
    `training_carbs_g = 0.0` internally and emitted `training_kcal = 0.0`.

### 9.3 Phase 9 CLI Contract Clarifications

-   Canonical production invocation path is `mealplan calculate`.
-   `--training-zones` accepts a JSON string only (for example `--training-zones '{"2": 45}'`).
-   Invalid `--training-zones` JSON is a validation-class failure and must map to exit code `2`.
-   `--format` supports only `json`, `text`, and `table`; default is `json`.
-   `--debug` does not alter successful output format or payload on stdout.
-   Without `--debug`, errors are concise single-line stderr messages.
-   With `--debug`, the same error additionally includes traceback details on stderr.

------------------------------------------------------------------------

## 10. Validation

-   Weight \> 0
-   Age \> 0
-   Height is integer and \> 0
-   Height does not have an upper bound
-   Numeric strings are not accepted for `--height` (strict integer input only)
-   `--training-zones` must be valid JSON object text when provided
-   Carb totals exact
-   Fat not negative
-   training-before required if training-zones provided

### 10.1 Canonical Exit Codes

-   `0`: success
-   `2`: validation/input failures (including typed flag parse errors and invalid training-zones JSON)
-   `3`: domain rule violations
-   `4`: runtime/infrastructure failures

------------------------------------------------------------------------

## 11. Definition of Done

-   Deterministic calculations
-   Redistribution logic tested
-   Macro totals validated
-   CLI handles invalid inputs
