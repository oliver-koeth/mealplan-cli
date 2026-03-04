# PRD: Enhance-001 Training Carb Meal and Kcal Breakdown

## 1. Introduction/Overview

This enhancement improves meal-plan output in two ways:
- It introduces a conditional `training` meal when training carbs are prescribed (`training_carbs_g > 0`).
- It adds per-meal calorie (`kcal`) output and guarantees reconciliation between summed meal kcal and day total kcal.

The goal is to make training-day plans operationally usable while keeping output deterministic and internally consistent.

## 2. Goals

- Add a dedicated `training` meal when proposed training carbs are greater than zero.
- Place the `training` meal before any meal according to `--training-before`.
- Allow syntactic `--training-before=training` parsing but reject it at semantic runtime validation.
- Include `kcal` for every meal in the output.
- Ensure sum of meal kcal equals top-level `TDEE` via deterministic evening-snack display-only kcal reconciliation for small rounding drift.

## 3. User Stories

### US-001: Insert conditional training meal based on training carbs
**Description:** As a user following a training-day plan, I want training carbs represented as a dedicated `training` meal so execution is clear.

**Acceptance Criteria:**
- [ ] When `training_carbs_g > 0`, meal-plan output includes exactly one `training` meal.
- [ ] The `training` meal carbohydrate amount equals the proposed training carb amount.
- [ ] The `training` meal has `protein_g=0` and `fat_g=0`.
- [ ] When `training_carbs_g = 0`, no `training` meal is included.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-002: Position training meal using existing `--training-before` logic
**Description:** As a user, I want the `training` meal inserted in a predictable place based on my existing sequencing option.

**Acceptance Criteria:**
- [ ] `training` meal insertion position is derived from current `--training-before` semantics.
- [ ] Insertion before any supported meal target works deterministically.
- [ ] `--training-before=training` is accepted syntactically but rejected by deterministic semantic runtime validation.
- [ ] Behavior explicitly accepts that training cannot be placed after evening snack.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Add per-meal kcal in meal-plan output
**Description:** As a user, I want calories shown per meal so I can validate energy distribution and track intake accurately.

**Acceptance Criteria:**
- [ ] Each meal row includes `kcal` in output alongside macros.
- [ ] `kcal` values are derived consistently using the project’s macro-to-kcal conversion rules.
- [ ] Output formatting remains stable and deterministic.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-004: Reconcile meal kcal sum to day total kcal
**Description:** As a user, I want meal kcal totals to match day total kcal exactly so totals are trustworthy.

**Acceptance Criteria:**
- [ ] Sum of displayed meal kcal equals displayed day total kcal.
- [ ] Small rounding drift is corrected by adjusting evening snack kcal only.
- [ ] Reconciliation target is top-level `TDEE`.
- [ ] Evening-snack adjustment is display-only for `kcal`; macro grams remain unchanged.
- [ ] Reconciliation is deterministic (same inputs produce same output).
- [ ] Reconciliation does not alter meal ordering.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-005: Cover edge cases and regression paths with automated tests
**Description:** As a maintainer, I want focused tests for insertion and kcal reconciliation so regressions are detected early.

**Acceptance Criteria:**
- [ ] Tests verify `training` meal present/absent for `training_carbs_g > 0` vs `= 0`.
- [ ] Tests verify insertion ordering across supported `--training-before` targets.
- [ ] Tests verify `--training-before=training` fails semantic runtime validation.
- [ ] Tests verify `training` meal macros are carbs-only (`protein_g=0`, `fat_g=0`).
- [ ] Tests verify meal-level `kcal` is included for all emitted meals.
- [ ] Tests verify exact equality between summed meal kcal and top-level `TDEE` after reconciliation.
- [ ] Tests verify display-only kcal reconciliation does not mutate macro grams.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-006: Update canonical docs for new meal/output contracts
**Description:** As a maintainer, I want canonical docs updated so the new meal-sequencing and kcal contract is explicit and durable.

**Acceptance Criteria:**
- [ ] Update `docs/REQUIREMENTS.md` with conditional training-meal insertion contract and semantic rejection rule for `--training-before=training`.
- [ ] Update `docs/MODEL.md` with response shape changes (optional training meal, per-meal `kcal`, training-meal macro composition).
- [ ] Update `docs/ARCHITECTURE.md` with display-only evening-snack kcal reconciliation behavior targeting top-level `TDEE`.
- [ ] Typecheck passes.
- [ ] Tests pass.

## 4. Functional Requirements

- FR-1: The system must add a `training` meal if and only if `training_carbs_g > 0`.
- FR-2: The `training` meal must contain the prescribed training carbohydrate amount.
- FR-3: The system must place `training` using existing `--training-before` sequencing behavior.
- FR-4: The system must allow syntactic `--training-before` parsing and reject `training` target at semantic runtime validation.
- FR-5: The system must emit `kcal` per meal in the meal-plan output.
- FR-5a: The `training` meal must be carbs-only (`carbs_g=training_carbs_g`, `protein_g=0`, `fat_g=0`).
- FR-6: The system must ensure summed meal kcal equals top-level `TDEE`.
- FR-7: The system must correct small kcal rounding drift by adjusting evening snack kcal only.
- FR-7a: Evening-snack reconciliation is display-only for `kcal` and must not mutate displayed macro grams.
- FR-8: The system must preserve deterministic ordering and deterministic reconciliation results.
- FR-9: The system must update canonical docs when this enhancement changes behavior/contracts.

## 5. Non-Goals (Out of Scope)

- Supporting placement of `training` after evening snack.
- Adding new CLI flags for training-meal placement.
- Reworking daily macro target computation logic beyond training-meal insertion and kcal reconciliation.
- Broad documentation rewrites unless canonical contracts change.

## 6. Design Considerations

- Keep training-meal insertion logic centralized near existing meal-order assembly to avoid divergent ordering rules.
- Keep kcal derivation and reconciliation explicit and auditable in one place.
- Preserve current meal naming and ordering conventions except for conditional insertion of `training`.

## 7. Technical Considerations

- Reuse existing domain constants/enums and current `--training-before` validation path.
- If `training` becomes a syntactically allowed target, semantic validation must still reject recursive placement with deterministic error handling.
- Implement kcal reconciliation as a final output-boundary step to avoid intermediate drift compounding.
- Keep correction strategy deterministic by targeting `evening-snack` only.
- Apply reconciliation as a display-layer kcal correction only; keep macro gram allocations unchanged.
- Ensure test coverage includes both deterministic nominal cases and rounding-drift cases.

## 8. Success Metrics

- Training-day outputs include correctly positioned `training` meal whenever training carbs are non-zero.
- Non-training outputs remain unchanged in meal count/structure except for added `kcal` field.
- Meal-level kcal sum matches top-level `TDEE` in all tested scenarios.
- No regressions in type checking and automated tests.
- Canonical docs describe the shipped contract without drift.

## 9. Open Questions

- None for this enhancement scope after clarification: evening-snack reconciliation is display-only for `kcal`.

## 10. Implementation Backlog (Enhance-001)

1. Update meal assembly logic to conditionally add `training` meal for `training_carbs_g > 0`.
2. Wire conditional insertion to `--training-before` ordering behavior before any meal target.
3. Ensure `--training-before=training` is accepted syntactically and rejected in semantic runtime validation.
4. Add per-meal `kcal` computation and output field.
5. Ensure `training` meal macro composition is carbs-only (`protein_g=0`, `fat_g=0`).
6. Add deterministic evening-snack kcal reconciliation so summed meal kcal equals top-level `TDEE` (display-only kcal correction; no macro-gram mutation).
7. Add/extend tests for presence/ordering/validation and kcal display/reconciliation.
8. Update `docs/REQUIREMENTS.md`, `docs/MODEL.md`, and `docs/ARCHITECTURE.md` for canonical contract changes.
9. Run full quality gates: typecheck and tests.
