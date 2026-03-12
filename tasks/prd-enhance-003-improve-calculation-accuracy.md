# PRD: Enhance-003 Improve Calculation Accuracy

## 1. Introduction/Overview

This enhancement replaces the current simplified training calorie-demand calculation with a more realistic VO2-based estimate that accounts for athlete characteristics and time spent in each of the five training zones.

Today, training demand is effectively modeled as a fixed number of kcal per minute, which ignores athlete age, gender, weight, and intensity distribution across zones. The new model introduces an optional `--vo2max` CLI parameter and otherwise predicts VO2max from age, gender, and weight in kilograms. The public response contract changes only at the top level: `training_carbs_g` is replaced by `training_kcal`. Existing training-fueling behavior and the optional `training` meal remain intact permanently; `training_carbs_g` continues to be used for planning and representing the fueling meal.

The goal is to improve calculation accuracy without forcing a full redesign of the current meal-planning pipeline in one step.

## 2. Goals

- Replace the fixed training calorie-demand rule with a zone-weighted VO2-based formula.
- Use athlete age, gender, and weight in kilograms when `--vo2max` is not provided.
- Add optional CLI input `--vo2max` as an integer.
- Validate `--vo2max` with a realistic integer range.
- Change only the top-level output field from `training_carbs_g` to `training_kcal`.
- Preserve existing internal training-fueling and optional `training` meal behavior as a permanent part of the model.
- Deliver the change in a phased backlog: formula/contract rollout first, then terminology/doc cleanup that preserves the permanent fueling model.

## 3. User Stories

### US-001: Accept explicit VO2max input from the CLI
**Description:** As a user, I want to provide my VO2max directly so that training calorie estimates can use athlete-specific fitness input when I know it.

**Acceptance Criteria:**
- [ ] The CLI accepts optional `--vo2max <integer>`.
- [ ] `--vo2max` is parsed into the application request contract as an optional field.
- [ ] Validation rejects non-integer values.
- [ ] Validation rejects values outside the inclusive range `10..100`.
- [ ] Omitting `--vo2max` remains valid.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-002: Predict VO2max when explicit input is missing
**Description:** As a user, I want the system to estimate VO2max from my profile so that I do not need to supply extra data for a more realistic training calorie estimate.

**Acceptance Criteria:**
- [ ] If `vo2max` is absent, the system calculates `vo2max_pred` using `weight_kg` directly with the canonical formula `79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)`.
- [ ] The implementation uses `sex = 0` for male and `sex = 1` for female.
- [ ] Weight remains in kilograms throughout the implementation; no pounds conversion is used.
- [ ] If `vo2max` is present, prediction is skipped and the explicit value is used instead.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Replace the training calorie-demand formula with a zone-weighted VO2-based estimate
**Description:** As a user, I want training calories to depend on athlete profile and zone distribution so that easy and hard sessions are no longer treated as equivalent.

**Acceptance Criteria:**
- [ ] The current fixed training calorie-demand rule is removed.
- [ ] The system uses the zone coefficients `z1=0.30`, `z2=0.50`, `z3=0.65`, `z4=0.80`, `z5=0.925`.
- [ ] For each zone, kcal/min is calculated as `weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)`.
- [ ] Total `training_kcal` equals the sum of `minutes_in_zone * kcal_per_min_for_zone` across zones `1..5`.
- [ ] Internal calculation uses full floating-point precision through downstream planning; rounding to `2` decimal places happens only on emitted fields.
- [ ] All-zero zone minutes produce `training_kcal = 0.0`.
- [ ] Zone 1 contributes non-zero kcal when zone 1 minutes are present and VO2max is valid.
- [ ] Higher zones produce higher kcal/min than lower zones for the same athlete.
- [ ] Public emitted `training_kcal` is rounded to `2` decimal places.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-004: Preserve current meal-planning behavior during the compatibility phase
**Description:** As a maintainer, I want the formula change to land without rewriting the entire training-meal pipeline so that the enhancement remains deliverable in a controlled way.

**Acceptance Criteria:**
- [ ] The enhancement replaces only `training_calorie_demand_kcal` in the current pipeline during the first implementation phase.
- [ ] Existing internal training-fueling behavior remains in place where currently required by meal construction.
- [ ] Existing optional `training` meal behavior remains intact during the first phase and after rollout.
- [ ] No new mandatory CLI inputs beyond optional `--vo2max` are introduced.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-005: Change the top-level response contract from `training_carbs_g` to `training_kcal`
**Description:** As a user of the structured output, I want the top-level training metric to reflect calorie demand rather than carb grams so that the response aligns with the improved formula.

**Acceptance Criteria:**
- [ ] Top-level JSON output includes `training_kcal`.
- [ ] Top-level JSON output no longer includes `training_carbs_g`.
- [ ] Top-level `total_kcal` equals `TDEE + training_kcal`, subject only to the final emitted-field rounding policy.
- [ ] Text output shows `training_kcal`.
- [ ] Table output shows `training_kcal`.
- [ ] Existing training meal behavior continues to use carb grams internally and in meal rows after this change.
- [ ] Output ordering rules and golden fixtures are updated deterministically.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-006: Keep regression coverage and canonical docs aligned with the phased contract
**Description:** As a maintainer, I want tests and docs updated so the staged rollout is explicit and protected from drift.

**Acceptance Criteria:**
- [ ] Tests cover explicit `vo2max` and predicted `vo2max` paths.
- [ ] Tests cover validation boundaries for `--vo2max` with accepted values inside `10..100` and rejected values outside that range.
- [ ] Tests cover zone-order monotonicity of kcal/min.
- [ ] Tests cover athlete-difference cases from age, gender, and weight changes when `vo2max` is predicted.
- [ ] Tests cover top-level response rename from `training_carbs_g` to `training_kcal`.
- [ ] Tests preserve current compatibility behavior for the optional `training` meal.
- [ ] Update `docs/REQUIREMENTS.md`, `docs/MODEL.md`, `docs/ARCHITECTURE.md`, and `README.md` where the enhancement changes canonical behavior or public examples.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-007: Clean up outdated top-level terminology after the rollout
**Description:** As a maintainer, I want a follow-up cleanup phase so that docs and helper descriptions clearly distinguish top-level training calories from the separate permanent fueling model.

**Acceptance Criteria:**
- [ ] Backlog explicitly separates the initial rollout from later cleanup work.
- [ ] Cleanup scope identifies outdated naming and documentation that still reflects the old top-level metric without removing the permanent fueling concept.
- [ ] Cleanup does not change the already-shipped public contract without explicit follow-up review.
- [ ] Typecheck passes for any cleanup changes.
- [ ] Tests pass for any cleanup changes.

## 4. Functional Requirements

- FR-1: The system must accept optional request/CLI input `vo2max` as an integer.
- FR-2: The system must validate `vo2max` as an integer in the inclusive range `10..100`.
- FR-3: The system must use explicit `vo2max` when provided.
- FR-4: The system must predict VO2max when explicit `vo2max` is absent.
- FR-5: The prediction formula must use `weight_kg` directly as `79.9 - (0.39 * age) - (13.7 * sex) - (0.28 * weight_kg)`.
- FR-6: The system must map `male -> 0` and `female -> 1` for the prediction formula.
- FR-7: The system must not convert weight to pounds anywhere in this enhancement.
- FR-8: The system must calculate zone-specific kcal/min as `weight_kg * 0.005 * zone_intensity * max(vo2max_used - 3.5, 0)`.
- FR-9: The system must use these fixed zone intensity coefficients:
- FR-9a: zone 1 => `0.30`
- FR-9b: zone 2 => `0.50`
- FR-9c: zone 3 => `0.65`
- FR-9d: zone 4 => `0.80`
- FR-9e: zone 5 => `0.925`
- FR-10: The system must calculate `training_kcal` as the sum across zones `1..5` of `zone_minutes * zone_kcal_per_min`.
- FR-11: The system must retain full floating-point precision for training-kcal calculation and downstream planning until response-boundary emission.
- FR-12: The system must round public emitted `training_kcal` to `2` decimal places.
- FR-13: If all zone minutes are zero, the system must emit `training_kcal = 0.0`.
- FR-14: Zone 1 minutes must contribute non-zero training calories under the new formula when athlete input is valid.
- FR-15: The first implementation phase must replace only `training_calorie_demand_kcal` in the current pipeline unless required for mechanical compatibility.
- FR-16: The system must preserve current internal training-fueling behavior where needed by current meal construction as a permanent part of the model.
- FR-17: The system must preserve current optional `training` meal behavior as a permanent part of the model.
- FR-18: The system must replace top-level response field `training_carbs_g` with `training_kcal`.
- FR-19: The system must set top-level `total_kcal` to `TDEE + training_kcal`, with emitted-value rounding applied only at the response boundary.
- FR-20: The system must update JSON, text, and table renderers to reflect `training_kcal`.
- FR-21: The system must update deterministic snapshots and canonical docs to reflect the new formula and top-level contract.
- FR-22: The backlog for this enhancement must include a follow-up cleanup phase for outdated internal terminology and remaining documentation drift.

## 5. Non-Goals (Out of Scope)

- Changing the BMR or TDEE formula.
- Changing `--activity` levels or activity multipliers.
- Requiring sport-specific modality inputs such as running pace, cycling power, terrain, or HR traces.
- Replacing the existing internal training-fueling model.
- Redesigning the optional `training` meal.
- Adding backward-compatible dual top-level fields for a transition period.
- Broad refactors unrelated to the training-calculation accuracy enhancement.

## 6. Design Considerations

- Keep `weight_kg` as the only public and internal weight unit for this enhancement.
- Make the VO2-based formula explicit in code and docs so coefficients are not inferred or scattered.
- Keep the rollout boundary narrow: new training calorie estimate in, existing fueling and meal-planning behavior otherwise unchanged.
- Treat the top-level contract rename as intentional and immediate rather than transitional.
- Keep internal training-carb concepts explicit because they remain part of the permanent fueling model.

## 7. Technical Considerations

- The current training-demand function likely needs a new signature because the formula now depends on athlete context in addition to zone minutes.
- Application contracts, parsing, validation, orchestration, CLI rendering, and golden fixtures all need coordinated updates because the request and response contracts both change.
- The current response and docs reference `training_carbs_g` in multiple places; these must be audited so top-level contract drift does not remain after rollout.
- The rollout should avoid unnecessary churn in meal assembly where internal training-carb behavior remains the source of the optional `training` meal.
- `total_kcal` should be pinned directly to `TDEE + training_kcal`; implementation should not leave this as an implicit consequence of older meal-budget semantics.
- Unit tests should pin the exact zone coefficients and kg-based VO2 prediction formula to prevent silent coefficient drift.

## 8. Success Metrics

- Training calorie estimates differ appropriately across athletes and zone distributions instead of collapsing to a fixed kcal-per-minute rule.
- Explicit `--vo2max` input and predicted VO2max both produce deterministic results.
- Top-level outputs consistently expose `training_kcal` instead of `training_carbs_g`.
- Existing optional training-meal behavior remains stable as part of the permanent model.
- Type checking and automated tests pass with updated regression and golden coverage.

## 9. Open Questions

- None for the initial PRD scope. The follow-up cleanup work is limited to clarity and terminology, not removal of the permanent fueling model.

## 10. Implementation Backlog (Enhance-003)

### Phase A: Compatibility Rollout

1. Extend request contracts, parsing, and CLI inputs to support optional integer `--vo2max`.
2. Add validation for `vo2max` as an integer in the inclusive range `10..100`.
3. Introduce canonical VO2max source selection logic: explicit input first, otherwise kg-based prediction from age, gender, and weight.
4. Replace the current training calorie-demand formula with the new VO2-based zone-weighted calculation.
5. Keep full floating-point precision internally for training-kcal calculation and downstream planning, and round only on emitted fields.
6. Update orchestration so the training-demand stage receives athlete age, gender, weight in kg, optional `vo2max`, and normalized zone minutes.
7. Update response contracts and renderers so the top level emits `training_kcal` instead of `training_carbs_g`, and pin top-level `total_kcal` to `TDEE + training_kcal`.
8. Preserve existing internal training-fueling and optional `training` meal behavior as permanent current meal-construction behavior.
9. Update unit, integration, CLI, and golden tests for the new formula, validation rules, top-level response rename, and pinned `total_kcal` semantics.
10. Update canonical docs and examples in `docs/REQUIREMENTS.md`, `docs/MODEL.md`, `docs/ARCHITECTURE.md`, and `README.md`.
11. Run full quality gates: typecheck and tests.

### Phase B: Cleanup and Terminology Alignment

1. Audit internal names, helper APIs, comments, and documentation that still imply the old top-level training metric.
2. Rename or clarify outdated internals where safe so the distinction between top-level `training_kcal` and permanent carb-based training-meal behavior is explicit.
3. Remove or rewrite stale examples and explanatory text that still present the old simplified training-demand model as canonical.
4. Add regression tests for any cleanup-driven renames or documentation-backed examples that change.
5. Run full quality gates: typecheck and tests.
