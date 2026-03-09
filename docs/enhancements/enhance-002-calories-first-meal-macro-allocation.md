# Enhancement Brief: enhance-002 Calories-First Meal Macro Allocation

## Problem statement
The current planning logic derives daily carbohydrate targets from `--carbs` mode (`3/5/4 g/kg`) and then allocates meal carbs directly from that target. Protein and fat are split independently, with equal protein/fat distribution across the six canonical meals and periodized carb allocation based on the current high-meal percentage rules.

The requested enhancement keeps TDEE, training calorie demand, and training fueling calculations unchanged, but replaces meal macro planning with a calories-first approach for the six normal meals. In the new model, total calories for the six normal meals are derived first, protein is fixed from bodyweight, meal carb strategy is assigned by meal, and each meal's remaining calories are converted into carbs and fat according to low/medium/high-carb meal ratios.

## Goals
- Preserve the existing calculations for:
  - TDEE
  - training calorie demand
  - training fueling (`carbs/hr`, then converted to kcal)
- Replace the current carb-target-first meal allocation logic with a calories-first allocation across the six canonical non-training meals.
- Keep the existing output shape except for the new per-meal `carbs_strategy` field; any protein-reduction warning is emitted to `stderr`, not added to the structured response payload.
- Make the new meal-planning rules explicit enough to implement without inferring unstated behavior.

## In scope
- Keep daily protein target as `2 * weight_kg`.
- Define the calorie budget for the six normal meals as:
  - `TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`
- Distribute the six normal-meal calorie budget across canonical meals using:
  - breakfast `2/9`
  - morning-snack `1/9`
  - lunch `2/9`
  - afternoon-snack `1/9`
  - dinner `2/9`
  - evening-snack `1/9`
- Define meal-level carb strategy selection:
  - `--carbs normal` => all meals `medium carbs`
  - `--carbs low` => all meals `low carbs`
  - `--carbs periodized` => baseline low-carb meals with explicit post-training and next-day overrides
- Distribute daily protein across the six canonical meals using the same `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` meal shares as calories.
- Derive per-meal carbs and fat from remaining meal calories after protein calories are assigned.
- Add per-meal `carbs_strategy` output with values `low`, `medium`, or `high`.
- Preserve current output ordering and the existing `training` meal behavior.

## Out of scope
- Changing TDEE formula or activity multipliers.
- Changing training calorie demand logic.
- Changing training fueling logic or the current training meal representation unless required by clarification.
- Changing CLI flag names or adding new CLI parameters.
- Reworking non-calculation concerns such as rendering style or command structure.

## Constraints and assumptions
- Existing Enhancement 001 behavior introduced:
  - optional `training` meal output when `training_carbs_g > 0`
  - per-meal `kcal`
  - top-level `total_kcal`
- This enhancement keeps the `training` meal behavior as-is: it represents carbs-only fueling for training.
- The six canonical meals remain:
  - `breakfast`
  - `morning-snack`
  - `lunch`
  - `afternoon-snack`
  - `dinner`
  - `evening-snack`
- "Caloric deficit from training" in the request is interpreted as the currently implemented `training_calorie_demand_kcal`.
- "Calories from fueling the training" is interpreted as `training_carbs_g * 4`.
- Meal carb strategy affects only the six normal meals; training fueling remains separate.
- Remaining normal-meal calories after protein are split by carb strategy as:
  - `low`: `1/4` of remaining meal calories from carbs, `3/4` from fat
  - `medium`: `2/3` of remaining meal calories from carbs, `1/3` from fat
  - `high`: `3/4` of remaining meal calories from carbs, `1/4` from fat
- Top-level `carbs_g` and `fat_g` become sums of derived meal macros rather than fixed `g/kg` targets.
- If any meal's protein allocation is reduced because its calorie budget is too small, top-level `protein_g` must also be reduced to match the final emitted meals.
- The `training` meal always uses `carbs_strategy=high`.
- For `--carbs periodized`:
  - baseline all meals are `low`
  - the meal at `--training-before` is the first post-training meal and becomes `high`
  - the next chronological meal becomes the second post-training `high` meal except:
    - if `--training-before=dinner`, only `dinner` is forced high and `evening-snack` remains low
    - if `--training-before=evening-snack`, only `evening-snack` is forced high and no wrap-to-breakfast high meal occurs
  - if `--training-tomorrow=high`, `dinner` is always `high`, including when this overrides the exception behavior above
- If protein calories allocated to a meal would exceed that meal's calorie budget, the planner must emit a warning and reduce that meal's protein allocation so remaining meal calories are at least `0`.
- Protein-reduction warnings are emitted to `stderr` on otherwise successful runs and do not alter the response schema.

## Definition of done
- The six normal meals use the new calorie shares `2/9, 1/9, 2/9, 1/9, 2/9, 1/9`.
- Daily protein target remains `2 * weight_kg`.
- Daily protein is distributed across meals using the same `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` shares.
- The six normal-meal calorie pool is calculated as:
  - `TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`
- Meal carb strategy assignment follows the requested `low`, `normal`, and `periodized` rules.
- For each normal meal:
  - meal protein is assigned from the daily protein target
  - remaining meal calories are computed after protein calories
  - remaining calories are split between carbs and fat according to meal carb strategy
- Top-level `carbs_g` and `fat_g` are calculated bottom-up from the final meal allocations.
- If protein reduction occurs for any meal, top-level `protein_g` is also calculated from the final emitted meal allocations rather than the original daily target.
- Training fueling calculations and training meal output behavior remain unchanged.
- Each meal row includes `carbs_strategy` with values `low`, `medium`, or `high`; the `training` meal always uses `high`.
- For `periodized`, `--training-tomorrow=high` forces `dinner` to `high` even when `--training-before` is `dinner` or `evening-snack`.
- For `periodized`, `--training-before=dinner` and `--training-before=evening-snack` do not wrap to create a second high-carb meal.
- If a meal's calorie budget cannot accommodate its initially assigned protein calories, the planner emits a warning and reduces that meal's protein so remaining meal calories are exactly `0` or greater.
- Protein-reduction warnings are emitted on `stderr` and are not added to JSON/text/table payload fields.
- Automated tests are updated to cover the new meal calorie split, macro derivation, and periodized edge cases.
- Canonical docs are updated because this changes core calculation behavior and invalidates current `3/5/4 g/kg` top-level carb-target semantics.

## Open questions
- None for this enhancement scope after clarification.
