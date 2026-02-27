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

(Height optional future extension; fixed defaults may apply if not
provided.)

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

1.  If not periodized → ignore redistribution
2.  Apply post-training high rule
3.  Apply next-day override unless conflict
4.  Ensure carb totals remain exact

------------------------------------------------------------------------

## 9. Output Format

JSON structure:

{ "TDEE": number, "training_carbs_g": number, "protein_g": number,
"carbs_g": number, "fat_g": number, "meals": \[
{"meal":"breakfast","carbs_g":x,"protein_g":y,"fat_g":z} \] }

------------------------------------------------------------------------

## 10. Validation

-   Weight \> 0
-   Age \> 0
-   Carb totals exact
-   Fat not negative
-   training-before required if training-zones provided

------------------------------------------------------------------------

## 11. Definition of Done

-   Deterministic calculations
-   Redistribution logic tested
-   Macro totals validated
-   CLI handles invalid inputs
