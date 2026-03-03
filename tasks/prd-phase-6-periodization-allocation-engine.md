# PRD: Phase 6 Periodization Allocation Engine

## 1. Introduction/Overview

Phase 6 implements deterministic carbohydrate periodization allocation across the six canonical meals.

This phase introduces the domain-only periodization allocator that redistributes daily carbs based on training timing and next-day load precedence:
- two post-training high-carb meals
- each high meal receives `30%` of total daily carbs
- remaining meals share residual carbs evenly
- next-day high-load override and conflict handling must follow documented precedence exactly

## 2. Goals

- Implement a pure domain periodization allocation engine with stable typed API.
- Enforce precedence exactly for post-training high meals and next-day high-load override conflicts.
- Keep behavior deterministic across runs for identical inputs.
- Use tolerance-based carb reconciliation (`abs(sum-target) <= 1e-9`) in Phase 6.
- Add exhaustive combinatorial tests across training meal positions, tomorrow-load states, and conflict branches.
- Define non-periodized bypass behavior deterministically for this phase.

## 3. User Stories

### US-001: Implement domain-only periodization allocation API
**Description:** As an orchestrator implementer, I want one pure domain allocation entrypoint so later orchestration can call periodization logic without duplicating rule code.

**Acceptance Criteria:**
- [ ] Add canonical Phase 6 API in `src/mealplan/domain/services.py` for carb allocation by meal.
- [ ] API is domain-only (no application wrapper and no CLI wiring in Phase 6).
- [ ] Function signature is typed and deterministic for identical inputs.
- [ ] Export the allocator via `src/mealplan/domain/__init__.py`.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-002: Implement post-training two-high-meal rule
**Description:** As a domain rule engine, I want the first two post-training meals marked high-carb so training timing drives carb concentration as specified.

**Acceptance Criteria:**
- [ ] The specified `training_before_meal` is treated as the first post-training high-carb meal.
- [ ] The immediately next chronological canonical meal is treated as the second high-carb meal.
- [ ] Each high-carb meal gets exactly `0.30 * daily_carbs`.
- [ ] Chronological next-meal logic handles end-of-day wrap deterministically in canonical order.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-003: Implement low-meal residual distribution
**Description:** As a domain rule engine, I want non-high meals to split remaining carbs evenly so total carbs are preserved and distribution is deterministic.

**Acceptance Criteria:**
- [ ] Remaining carbs are computed as `daily_carbs - sum(high_meal_allocations)`.
- [ ] Remaining carbs are divided evenly across the four non-high meals.
- [ ] Output includes all six canonical meals exactly once.
- [ ] Allocation order matches canonical meal order.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-004: Implement next-day high-load override with conflicts
**Description:** As a domain rule engine, I want tomorrow-high override behavior applied with explicit conflict handling so precedence remains stable and predictable.

**Acceptance Criteria:**
- [ ] When `training_load_tomorrow == high`, apply rule `dinner high`, `evening-snack low`.
- [ ] Override is skipped where conflict rules require preserving post-training precedence.
- [ ] Conflict cases where `training_before_meal` is `dinner` or `evening-snack` are handled explicitly and deterministically.
- [ ] No implicit tie-breaking exists outside documented precedence.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-005: Enforce precedence ordering explicitly
**Description:** As a maintainer, I want precedence encoded in one explicit sequence so future changes cannot silently reorder rules.

**Acceptance Criteria:**
- [ ] Rule execution order is explicit and documented in code/tests:
  1. Non-periodized bypass
  2. Post-training high rule
  3. Next-day high override unless conflict
  4. Reconciliation check
- [ ] Tests assert precedence outcomes, not just end totals.
- [ ] Deterministic behavior is preserved for identical inputs.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-006: Implement deterministic non-periodized bypass behavior
**Description:** As a caller, I want a deterministic return shape when carb mode is not periodized so Phase 6 behavior is explicit before Phase 7 meal assembly.

**Acceptance Criteria:**
- [ ] For non-`periodized` modes, allocator bypasses redistribution rules.
- [ ] Bypass returns a deterministic canonical equal-split placeholder allocation map.
- [ ] Bypass behavior is documented as Phase 6 placeholder semantics for later Phase 7 integration.
- [ ] Tests cover `low` and `normal` bypass cases with deterministic expected values.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-007: Add tolerance-based carb reconciliation check
**Description:** As a domain integrity guard, I want reconciliation validation with stable numeric tolerance so allocation totals remain correct without brittle float failures.

**Acceptance Criteria:**
- [ ] Add reconciliation check: `abs(sum_allocated_carbs - daily_carbs) <= 1e-9`.
- [ ] Reconciliation failure raises deterministic `DomainRuleError`.
- [ ] Error category/message prefix is stable for testing and exit-code mapping.
- [ ] Tests include pass and fail reconciliation scenarios.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-008: Add exhaustive combinatorial precedence/conflict matrix tests
**Description:** As a maintainer, I want full combinatorial coverage across precedence dimensions so regressions in complex rule interactions are caught immediately.

**Acceptance Criteria:**
- [ ] Add exhaustive matrix over:
  - all `training_before_meal` values
  - all `training_load_tomorrow` states (`low`, `medium`, `high`)
  - conflict and non-conflict branches
- [ ] Matrix asserts both meal-role selection (high/low placement) and exact/tolerance totals.
- [ ] Tests use deterministic expected outputs and stable case IDs.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-009: Document Phase 6 allocator boundaries and contracts
**Description:** As a contributor, I want clear contract documentation for periodization allocation so future phases integrate correctly without boundary leakage.

**Acceptance Criteria:**
- [ ] Update `docs/ARCHITECTURE.md` with Phase 6 technical boundary/API and precedence narrative.
- [ ] Update `docs/REQUIREMENTS.md` with functional periodization and override behavior clarifications as needed.
- [ ] Update `docs/MODEL.md` with canonical domain contract details for Phase 6 allocator inputs/outputs.
- [ ] Documentation explicitly states tolerance policy (`1e-9`) and deterministic non-periodized bypass behavior.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

## 4. Functional Requirements

- FR-1: The system must provide a pure domain periodization allocator API in `domain` with typed deterministic behavior.
- FR-2: The system must apply periodization redistribution only for `carb_mode = periodized`.
- FR-3: For periodized mode, the first two post-training meals must be high-carb, starting at `training_before_meal` then next canonical meal.
- FR-4: Each high-carb meal must receive exactly `30%` of daily carbs.
- FR-5: Remaining carbs must be split evenly across the remaining non-high meals.
- FR-6: If tomorrow load is `high`, the system must apply dinner-high/evening-snack-low override unless conflict rules preserve post-training precedence.
- FR-7: Precedence order must be explicit and deterministic: bypass -> post-training rule -> override/conflict handling -> reconciliation.
- FR-8: Non-periodized modes must bypass redistribution and return deterministic canonical equal-split placeholder allocation map.
- FR-9: Carb reconciliation must satisfy `abs(sum_allocated_carbs - daily_carbs) <= 1e-9`; otherwise deterministic domain error is raised.
- FR-10: Allocation output must include six unique canonical meals in canonical order.
- FR-11: Phase 6 behavior must be covered by exhaustive combinatorial precedence/conflict tests.
- FR-12: Phase 6 implementation must not introduce CLI or application-layer wiring.

## 5. Non-Goals (Out of Scope)

- Phase 7 meal macro assembly and output rounding-boundary residual adjustment policy.
- Phase 8 end-to-end orchestration wiring across the full calculation pipeline.
- Phase 9 CLI parsing/output behavior changes.
- Reworking Phase 3 semantic input validation responsibilities.
- Introducing persistence, external integrations, or non-deterministic runtime behavior.

## 6. Design Considerations

- Keep allocator logic centralized to avoid duplicated precedence behavior across modules.
- Represent meal roles and allocations in canonical order to simplify deterministic assertions.
- Keep rule steps explicit and named to support readable precedence-focused tests.

## 7. Technical Considerations

- Reuse canonical meal ordering constants and enums from existing domain model modules.
- Keep floating-point handling consistent with Phase 6 tolerance-based reconciliation.
- Preserve error taxonomy compatibility (`DomainRuleError`) for downstream exit-code mapping.
- Prefer parameterized/combinatorial tests with stable IDs for maintainability.

## 8. Success Metrics

- Exhaustive precedence/conflict matrix passes consistently.
- Allocation output remains deterministic for repeated identical inputs.
- Carb reconciliation stays within `1e-9` tolerance across covered scenarios.
- No boundary leakage: Phase 6 changes remain in domain/tests/docs without CLI/application wiring.

## 9. Open Questions

- None for Phase 6 scope after clarification decisions (`domain-only`, deterministic non-periodized bypass placeholder map, tolerance reconciliation, exhaustive combinatorial tests).

## 10. Implementation Backlog (Phase 6)

1. Add typed periodization allocator API in `src/mealplan/domain/services.py` and export via `mealplan.domain`.
2. Implement post-training two-high-meal selection in canonical order with deterministic wrap behavior.
3. Implement high-meal `30%` allocation and low-meal residual even split.
4. Implement tomorrow-high override and explicit conflict handling (`dinner`/`evening-snack` conflict scenarios).
5. Encode and document explicit precedence execution order in implementation/tests.
6. Implement non-periodized bypass returning deterministic canonical equal-split placeholder allocation map.
7. Add reconciliation check with tolerance `abs(sum-target) <= 1e-9` and deterministic `DomainRuleError` on failure.
8. Add exhaustive combinatorial test matrix across training meal positions, tomorrow-load states, and conflict branches.
9. Update `docs/ARCHITECTURE.md`, `docs/REQUIREMENTS.md`, and `docs/MODEL.md` for Phase 6 contracts and boundaries.
10. Run `ruff check .`, `mypy --strict src`, and `pytest`.
