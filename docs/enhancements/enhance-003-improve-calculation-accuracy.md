# Enhancement Brief: enhance-003 Improve Calculation Accuracy

## Problem statement
The current training energy calculation is intentionally simple:

- `training_calorie_demand_kcal = total training minutes * 4`
- training fueling is modeled separately via `training_carbs_g`

This is easy to reason about, but it is not realistic enough for endurance use cases because it ignores athlete characteristics and treats all training minutes as equally expensive regardless of intensity. A 60-minute zone 1 session and a 60-minute zone 5 session should not produce the same training calorie demand.

The requested enhancement replaces the current simplified training calorie demand formula with a more realistic zone-weighted estimate based on:

- athlete age
- athlete weight
- athlete gender
- time in training zones 1 through 5
- optional explicit VO2max input

## Goals
- Replace the current fixed `4 kcal/min` training demand rule with a VO2-based zone-weighted estimate.
- Keep athlete weight in kilograms throughout the calculation model, implementation, and public contract.
- Add a new CLI parameter `--vo2max` that allows explicit VO2max input as an integer.
- When `--vo2max` is omitted, estimate VO2max from age, gender, and weight.
- Change the top-level output contract so the response emits `training_kcal` instead of `training_carbs_g`.
- Make the new calculation precise enough to implement without inferring missing constants or unit conversions.

## In scope
- Introduce a canonical training calorie calculation that uses:
  - `age`
  - `gender`
  - `weight_kg`
  - normalized minutes in zones `1..5`
  - explicit `vo2max` if provided, otherwise predicted VO2max
- Add optional CLI input:
  - `--vo2max <integer>`
- Define the prediction formula used when `--vo2max` is missing.
- Define the fixed zone intensity coefficients used by the new model.
- Replace the current `training_calorie_demand_kcal` calculation logic with the new formula.
- Replace top-level response field `training_carbs_g` with `training_kcal`.
- Update docs, validation, tests, and examples affected by the contract change.

## Out of scope
- Changing the BMR or TDEE formula.
- Changing the existing `--activity` levels or activity multipliers.
- Adding support for sport-specific calorie models based on power, pace, speed, terrain, or device HR traces.
- Requiring the user to provide lactate threshold, HRmax, resting HR, FTP, or modality.
- Defining separate fueling recommendations in grams of carbohydrate for training intake.

## Canonical calculation

### Inputs
- `weight_kg` is always in kilograms.
- `age` is in years.
- `gender` uses the existing canonical enum values.
- `zones_minutes` is the normalized canonical zone-minute mapping for zones `1..5`.
- `vo2max` is an optional integer input from the CLI and contracts.

### VO2max source selection
- If `vo2max` is provided, use it directly.
- If `vo2max` is omitted, compute `vo2max_pred` using:

```text
sex = 0 for male, 1 for female

vo2max_pred =
  79.9
  - (0.39 * age)
  - (13.7 * sex)
  - (0.28 * weight_kg)
```

- The model must keep `weight_kg` as the canonical stored and passed weight unit.
- No pounds conversion is used anywhere in the implementation of this enhancement.

### Zone intensity coefficients
Use these fixed intensity coefficients:

- zone 1 => `0.30`
- zone 2 => `0.50`
- zone 3 => `0.65`
- zone 4 => `0.80`
- zone 5 => `0.925`

These coefficients are interpreted as pragmatic VO2-reserve intensity anchors for the five training zones.

### Training calorie demand formula
For each zone:

```text
net_kcal_per_min_for_zone =
  weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)
```

Total training calories:

```text
training_kcal =
  sum(
    zones_minutes[zone] * net_kcal_per_min_for_zone
    for zone in 1..5
  )
```

Equivalent compact form:

```text
training_kcal =
  0.005
  * weight_kg
  * max(vo2max_used - 3.5, 0)
  * (
      0.30 * z1_minutes
    + 0.50 * z2_minutes
    + 0.65 * z3_minutes
    + 0.80 * z4_minutes
    + 0.925 * z5_minutes
    )
```

### Rounding
- Internal calculation may use full floating-point precision.
- Public emitted `training_kcal` should be rounded to `2` decimal places, consistent with other kcal outputs.

## Contract changes

### Request/input changes
- Add optional request field `vo2max`.
- Add optional CLI flag `--vo2max`.
- `--vo2max` accepts integer input only.
- If `--vo2max` is missing, the application must calculate predicted VO2max from age, gender, and weight.

### Response/output changes
- Replace top-level field `training_carbs_g` with `training_kcal`.
- JSON, text, and table outputs must all reflect this rename.
- Ordering rules and golden fixtures must be updated accordingly.

## Behavioral expectations
- If all zone minutes are zero, `training_kcal` must be `0.0`.
- Zone 1 contributes non-zero training calories under the new model.
- Higher zones must contribute more kcal per minute than lower zones for the same athlete.
- A larger `vo2max` must increase estimated training kcal for the same athlete, zone distribution, and duration.
- Explicit `--vo2max` overrides prediction.
- When `--vo2max` is omitted, two athletes with different age, weight, or gender may produce different `training_kcal` for the same zone durations.

## Required implementation updates
- Update application contracts to include optional `vo2max` on input and `training_kcal` on output.
- Update CLI parsing, help text, and error handling for `--vo2max`.
- Replace the current domain API used for training demand with a function that accepts athlete context in addition to zone minutes.
- Update orchestration so the training calculation stage uses:
  - request age
  - request gender
  - request weight in kg
  - optional request VO2max
  - normalized zone minutes
- Remove any remaining top-level dependency on `training_carbs_g` in rendered output.
- Update canonical docs and examples that still describe `training_carbs_g` as the top-level training metric.

## Constraints and assumptions
- `weight` continues to be provided and stored in kilograms only.
- This enhancement changes training calorie demand estimation but does not change TDEE calculation.
- Existing activity multipliers remain baseline non-training activity multipliers.
- The new formula is an estimate and is intentionally sport-agnostic; no modality-specific coefficient is introduced in this enhancement.
- The formula must not require any additional mandatory CLI flags beyond `--vo2max`.
- Validation should reject invalid `vo2max` values consistently with other numeric input validation.
- If the predicted VO2max expression yields a value less than `3.5`, the calorie formula uses `max(vo2max_used - 3.5, 0)` so training kcal does not become negative.

## Definition of done
- The fixed `total_minutes * 4` training calorie demand rule is removed.
- Training calorie demand is calculated using the canonical VO2-based zone-weighted formula defined above.
- CLI supports optional `--vo2max` integer input.
- Missing `--vo2max` triggers the canonical prediction formula.
- Top-level response emits `training_kcal` and no longer emits `training_carbs_g`.
- JSON/text/table output snapshots are updated and deterministic.
- Automated tests cover:
  - explicit VO2max path
  - predicted VO2max path
  - all-zero training zones => `training_kcal = 0.0`
  - zone ordering monotonicity (`z5 kcal/min > z4 > z3 > z2 > z1`)
  - athlete-difference cases from age/weight/gender changes
  - CLI parsing and validation for `--vo2max`
  - response contract rename from `training_carbs_g` to `training_kcal`
- Core docs are updated because this changes both calculation behavior and the public response schema.

## Open questions
- None for this enhancement scope after the current clarification.
