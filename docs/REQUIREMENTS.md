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

  `--training-before`          enum           breakfast / morning-snack /
                                              lunch / afternoon-snack /
                                              dinner / evening-snack
  ------------------------------------------------------------------------

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

## 5. Training Fueling

-   If ALL training is Z1 → 0g carbs
-   If ANY zone ≥ Z2 → 60g carbs per hour

training_carbs_g = duration_minutes × (60 / 60)

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

{ "TDEE": number, "training_carbs_g": number, "protein_g": number,
"carbs_g": number, "fat_g": number, "meals": \[
{"meal":"breakfast","carbs_g":x,"protein_g":y,"fat_g":z} \] }

### 9.1 Phase 7 Assembly and Rounding Contract

-   Canonical meal-assembly API is domain-only in Phase 7:
    `calculate_meal_split_and_response_payload(tdee_kcal, training_carbs_g, protein_g, carbs_g, fat_g, carb_allocation_g_by_meal)`.
-   Response `meals` must contain exactly six canonical entries in this order:
    `breakfast`, `morning-snack`, `lunch`, `afternoon-snack`, `dinner`, `evening-snack`.
-   Per-meal `carbs_g`, `protein_g`, and `fat_g` values are rounded to 2 decimals at output boundary only.
-   Top-level fields (`TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`) remain canonical inputs and are not re-derived from rounded meal rows.
-   If rounded meal totals drift from top-level targets, residual correction is applied only to `evening-snack`.
-   Residual macro correction order is deterministic and fixed:
    `carbs_g`, then `protein_g`, then `fat_g`.

### 9.2 Phase 8 Application Orchestration Flow

-   Canonical application orchestration API is:
    `MealPlanCalculationService.calculate(request: MealPlanRequest) -> MealPlanResponse`.
-   The orchestration flow is validation-first and deterministic:
    1. `validate_meal_plan_flow` (schema + semantic + invariant gate)
    2. training-session normalization
    3. energy calculation
    4. macro target calculation
    5. training fueling calculation
    6. carb periodization allocation
    7. meal assembly and `MealPlanResponse` model validation
-   `training_session` is optional at the request boundary.
-   If `training_session` is omitted (`null`/`None`), orchestration must treat it as zero training with canonical defaults:
    - `zones_minutes = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}`
    - `training_before_meal = null`
-   For omitted training sessions, calculation proceeds normally and `training_carbs_g` must be `0.0`.

------------------------------------------------------------------------

## 10. Validation

-   Weight \> 0
-   Age \> 0
-   Height is integer and \> 0
-   Height does not have an upper bound
-   Numeric strings are not accepted for `--height` (strict integer input only)
-   Carb totals exact
-   Fat not negative
-   training-before required if training-zones provided

------------------------------------------------------------------------

## 11. Definition of Done

-   Deterministic calculations
-   Redistribution logic tested
-   Macro totals validated
-   CLI handles invalid inputs
