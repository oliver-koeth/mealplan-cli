# PRD: Enhance-002 Calories-First Meal Macro Allocation

## 1. Introduction/Overview

This enhancement replaces the current carb-target-first meal allocation model with a calories-first model for the six canonical non-training meals. Existing TDEE, training calorie demand, and training fueling calculations remain unchanged, but normal-meal calories are now budgeted first, protein is fixed from bodyweight, and the remaining meal calories are converted into carbs and fat according to a per-meal carbohydrate strategy.

The goal is to make meal planning align with the requested calorie budget while preserving current training-fueling behavior, output ordering, and command-line interface shape.

## 2. Goals

- Preserve current TDEE, training calorie demand, and training fueling calculations.
- Replace current normal-meal carb allocation logic with a calories-first allocation model.
- Keep daily protein target fixed at `2 * weight_kg`.
- Derive top-level `carbs_g` and `fat_g` from final meal allocations rather than from fixed daily `g/kg` targets.
- Add explicit per-meal `carbs_strategy` output without otherwise restructuring the response.
- Cover periodized edge cases and protein-overflow handling with deterministic tests.
- Keep the enhancement implementable as one coherent delivery within a single PRD/backlog.

## 3. User Stories

### US-001: Compute the six-meal calorie pool from existing day and training energy values
**Description:** As a user, I want the six normal meals to be derived from a clear calorie budget so that meal planning reflects both total energy needs and training fueling.

**Acceptance Criteria:**
- [ ] The six normal-meal calorie pool is calculated as `TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`.
- [ ] `training_calorie_supply_kcal` continues to equal `training_carbs_g * 4`.
- [ ] Existing TDEE and training calorie demand calculations are unchanged.
- [ ] Existing training fueling calculations are unchanged.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-002: Distribute normal-meal calories and protein by canonical meal shares
**Description:** As a user, I want calories and protein distributed predictably across the six canonical meals so that meal plans remain easy to follow.

**Acceptance Criteria:**
- [ ] The six canonical meals remain `breakfast`, `morning-snack`, `lunch`, `afternoon-snack`, `dinner`, and `evening-snack`.
- [ ] Normal-meal calories are distributed with shares `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` in canonical meal order.
- [ ] Daily protein target remains `2 * weight_kg`.
- [ ] Daily protein is distributed across the six canonical meals using the same `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` shares.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Assign per-meal carbohydrate strategy from the existing `--carbs` modes
**Description:** As a user, I want each meal to have an explicit carb strategy so that meal composition follows the selected low, normal, or periodized behavior.

**Acceptance Criteria:**
- [ ] For `--carbs normal`, all six canonical meals use `carbs_strategy=medium`.
- [ ] For `--carbs low`, all six canonical meals use `carbs_strategy=low`.
- [ ] For `--carbs periodized`, baseline all six canonical meals use `carbs_strategy=low` before overrides are applied.
- [ ] Each normal meal row includes `carbs_strategy` with one of `low`, `medium`, or `high`.
- [ ] Training meal behavior remains separate and is not redefined by this story.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-004: Apply deterministic periodized post-training and next-day overrides
**Description:** As a user training with periodized carbs, I want the correct meals upgraded to high-carb status so that the plan matches the enhancement rules exactly.

**Acceptance Criteria:**
- [ ] For `--carbs periodized`, the meal at `--training-before` becomes the first post-training `high` meal.
- [ ] The next chronological meal becomes the second post-training `high` meal except where explicit exceptions apply.
- [ ] If `--training-before=dinner`, only `dinner` is forced `high` and `evening-snack` remains `low` unless another rule overrides it.
- [ ] If `--training-before=evening-snack`, only `evening-snack` is forced `high` and no wrap-to-breakfast high meal occurs unless another rule overrides it.
- [ ] If `--training-tomorrow=high`, `dinner` is always `high`, including when this overrides the dinner/evening-snack exceptions above.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-005: Derive per-meal carbs and fat from remaining calories after protein
**Description:** As a user, I want each normal meal’s carbs and fat to be derived from its calorie budget after protein is assigned so that meal macros reconcile to the calories-first model.

**Acceptance Criteria:**
- [ ] For each normal meal, protein calories are assigned first using the meal’s protein grams.
- [ ] Remaining meal calories are computed after subtracting protein calories from the meal calorie budget.
- [ ] For `carbs_strategy=low`, `1/4` of remaining meal calories become carbs and `3/4` become fat.
- [ ] For `carbs_strategy=medium`, `2/3` of remaining meal calories become carbs and `1/3` become fat.
- [ ] For `carbs_strategy=high`, `3/4` of remaining meal calories become carbs and `1/4` become fat.
- [ ] Top-level `carbs_g` equals the sum of final meal carbs across all emitted meals.
- [ ] Top-level `fat_g` equals the sum of final meal fat across all emitted meals.
- [ ] Training meal output behavior remains unchanged except that its `carbs_strategy` output is always `high`.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-006: Handle protein-overflow meals with warning-only reduction behavior
**Description:** As a user, I want the planner to degrade predictably when a meal’s calorie budget cannot support its assigned protein so that outputs remain valid and the problem is visible.

**Acceptance Criteria:**
- [ ] If a meal’s initially assigned protein calories exceed that meal’s calorie budget, the planner reduces that meal’s protein allocation so remaining meal calories are `0` or greater.
- [ ] If protein reduction occurs for any meal, top-level `protein_g` equals the sum of final emitted meal protein rather than the original daily target.
- [ ] The planner emits a warning to `stderr` on otherwise successful runs when protein reduction occurs.
- [ ] The warning is not added to JSON, text, or table payload fields.
- [ ] No negative remaining meal calories are used to derive carbs or fat.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-007: Preserve output contract and ordering while adding `carbs_strategy`
**Description:** As a user, I want the enhancement to fit into the current output contract so that existing workflows need minimal adjustment.

**Acceptance Criteria:**
- [ ] Existing meal output ordering is preserved.
- [ ] Existing `training` meal behavior remains unchanged.
- [ ] Each canonical normal meal row includes the new `carbs_strategy` field.
- [ ] No CLI flag names are changed and no new CLI parameters are introduced.
- [ ] Protein-reduction warnings are emitted only to `stderr`.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-008: Update regression coverage and canonical docs for the new behavior
**Description:** As a maintainer, I want tests and canonical docs updated so the new calories-first contract is explicit and protected from regressions.

**Acceptance Criteria:**
- [ ] Tests cover the new six-meal calorie split and protein split using `2/9, 1/9, 2/9, 1/9, 2/9, 1/9`.
- [ ] Tests cover top-level `carbs_g` and `fat_g` being derived bottom-up from final meal allocations.
- [ ] Tests cover `normal`, `low`, and `periodized` carb-strategy assignment.
- [ ] Tests cover periodized edge cases for `--training-before=dinner` and `--training-before=evening-snack`.
- [ ] Tests cover `--training-tomorrow=high` forcing `dinner` to `high`.
- [ ] Tests cover protein-reduction warning behavior and non-negative meal remainder handling.
- [ ] Update `docs/REQUIREMENTS.md`, `docs/MODEL.md`, `docs/ARCHITECTURE.md`, and `docs/PLAN.md` where the enhancement changes canonical behavior or contracts.
- [ ] Typecheck passes.
- [ ] Tests pass.

## 4. Functional Requirements

- FR-1: The system must calculate the six normal-meal calorie pool as `TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`.
- FR-2: The system must keep TDEE, training calorie demand, and training fueling calculations unchanged.
- FR-3: The system must distribute the six normal-meal calorie pool across canonical meals using shares `2/9, 1/9, 2/9, 1/9, 2/9, 1/9`.
- FR-4: The system must keep the daily protein target at `2 * weight_kg`.
- FR-5: The system must distribute daily protein across canonical meals using the same `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` shares.
- FR-6: The system must assign `carbs_strategy=medium` to all normal meals for `--carbs normal`.
- FR-7: The system must assign `carbs_strategy=low` to all normal meals for `--carbs low`.
- FR-8: The system must assign baseline `carbs_strategy=low` to all normal meals for `--carbs periodized` before overrides.
- FR-9: The system must mark the meal at `--training-before` as the first post-training `high` meal in periodized mode.
- FR-10: The system must mark the next chronological meal as the second post-training `high` meal in periodized mode except for explicit dinner and evening-snack exceptions.
- FR-11: The system must not wrap from `evening-snack` to `breakfast` when assigning a second post-training high-carb meal.
- FR-12: The system must force `dinner` to `high` when `--training-tomorrow=high` in periodized mode, including when this overrides dinner/evening-snack exception outcomes.
- FR-13: The system must assign protein calories before deriving remaining calories for carbs and fat in each normal meal.
- FR-14: The system must derive per-meal carbs and fat from remaining meal calories using the existing low/medium/high-carb ratio rules.
- FR-14a: For `low` strategy, `1/4` of remaining meal calories must be converted to carbs and `3/4` to fat.
- FR-14b: For `medium` strategy, `2/3` of remaining meal calories must be converted to carbs and `1/3` to fat.
- FR-14c: For `high` strategy, `3/4` of remaining meal calories must be converted to carbs and `1/4` to fat.
- FR-15: The system must emit `carbs_strategy` for each canonical normal meal with values limited to `low`, `medium`, or `high`.
- FR-15a: The system must emit `carbs_strategy=high` for the `training` meal.
- FR-16: The system must derive top-level `carbs_g` and `fat_g` as sums of final meal allocations rather than fixed daily `g/kg` targets.
- FR-16a: If any meal protein allocation is reduced, the system must derive top-level `protein_g` from final emitted meal allocations.
- FR-17: The system must keep the current training meal representation and behavior unchanged.
- FR-18: If assigned protein calories exceed a meal’s calorie budget, the system must reduce that meal’s protein allocation until remaining calories are `0` or greater.
- FR-19: The system must emit protein-reduction warnings to `stderr` only and must not alter the structured response schema with warning fields.
- FR-20: The system must preserve meal ordering and existing CLI flag names/parameters.
- FR-21: The system must update canonical documentation because this enhancement changes core output semantics and meal-allocation behavior.

## 5. Non-Goals (Out of Scope)

- Changing the TDEE formula or activity multipliers.
- Changing training calorie demand logic.
- Changing training fueling logic or redefining the training meal.
- Adding new CLI flags or renaming existing CLI flags.
- Reworking rendering style, command structure, or unrelated output formatting.
- Rewriting all repository docs beyond the canonical docs affected by the contract change.

## 6. Design Considerations

- Keep the six canonical normal meals unchanged so existing sequencing and output expectations remain recognizable.
- Keep periodized override logic explicit and centralized so edge cases do not drift across layers.
- Treat `carbs_strategy` as a first-class output field for normal meals to make the derived macro logic inspectable.
- Preserve current output ordering to minimize downstream breakage.

## 7. Technical Considerations

- Implement the calories-first allocation close to the existing meal-allocation engine so the day-level energy and meal output logic stay coherent.
- Ensure top-level carb and fat totals are computed from final emitted meals, including any unchanged training meal behavior where applicable.
- Ensure top-level protein is recomputed from emitted meals only in the rare overflow case where a meal protein allocation is reduced.
- Keep warning emission separate from the structured response payload so CLI rendering and machine-readable output contracts remain stable.
- Update golden tests if output payload values or shapes change under the new allocation model.

## 8. Success Metrics

- Six normal meals are budgeted from the new calories-first formula in all tested scenarios.
- `normal`, `low`, and `periodized` meal strategies produce deterministic `carbs_strategy` assignments.
- Top-level `carbs_g` and `fat_g` reconcile to summed meal allocations in all tested scenarios.
- Periodized edge cases behave exactly as specified for `dinner`, `evening-snack`, and `training-tomorrow=high`.
- Protein-overflow scenarios produce a warning and valid non-negative meal remainder behavior.
- Type checking and automated tests pass with updated golden coverage.

## 9. Open Questions

- None for this enhancement scope after reviewing the enhancement brief. The brief is specific enough to implement the feature in one PRD.

## 10. Implementation Backlog (Enhance-002)

1. Refactor meal-allocation logic to calculate the six normal-meal calorie pool from `TDEE + training_calorie_demand_kcal - training_calorie_supply_kcal`.
2. Apply canonical `2/9, 1/9, 2/9, 1/9, 2/9, 1/9` shares to both normal-meal calories and daily protein.
3. Introduce meal-level carb-strategy assignment for `normal`, `low`, and baseline `periodized` modes.
4. Implement deterministic periodized override logic for post-training meals, dinner/evening-snack exceptions, and `--training-tomorrow=high`.
5. Derive each normal meal’s carbs and fat from remaining calories after protein calories are assigned, using existing low/medium/high-carb ratio rules.
6. Recompute top-level `carbs_g` and `fat_g` from final meal allocations, and recompute top-level `protein_g` when overflow-driven meal protein reduction occurs, while preserving unchanged training meal behavior.
7. Add warning-only protein-reduction handling for meals whose calorie budget cannot support their assigned protein.
8. Update response assembly so canonical normal meals emit `carbs_strategy` without disturbing ordering or CLI shape.
9. Update unit, integration, and golden coverage for calorie shares, strategy assignment, periodized edge cases, bottom-up macro totals, and warning behavior.
10. Update canonical docs in `docs/REQUIREMENTS.md`, `docs/MODEL.md`, `docs/ARCHITECTURE.md`, and `docs/PLAN.md`.
11. Run full quality gates: typecheck and tests.
