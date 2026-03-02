# PRD: Phase 3 Validation Layer

## 1. Introduction/Overview

Phase 3 introduces business-rule validation and domain invariant enforcement for `mealplan` on top of the Phase 2 canonical contracts.  
The goal is deterministic fail-fast behavior for invalid semantic inputs and invalid computed/assembled domain states, without implementing Phase 4+ calculation engines in this phase.

This phase follows the agreed layering split:
- Semantic input validation in `application`
- Domain invariants in `domain`
- `application` orchestrates both and maps failures to typed errors

## 2. Goals

- Enforce semantic input rules beyond schema shape checks.
- Enforce domain invariants as reusable domain-level validation.
- Keep validation deterministic and free of side effects.
- Preserve typed error behavior (`ValidationError` vs `DomainRuleError`) and exit-code mapping.
- Add a focused invalid-input and invariant-failure test matrix.

## 3. User Stories

### US-001: Add application-level semantic input validator
**Description:** As an application service, I want semantic validation after contract parsing so invalid inputs are rejected before domain calculations run.

**Acceptance Criteria:**
- [ ] Add application validator entrypoint that accepts parsed `MealPlanRequest`
- [ ] Validator checks `age > 0` and `weight_kg > 0` as semantic guards
- [ ] Semantic validator is callable independently from CLI code
- [ ] Validation failures return deterministic `ValidationError` payloads
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-002: Enforce training dependency rule in application layer
**Description:** As a user, I want a clear validation error when training minutes are present but `training_before_meal` is missing.

**Acceptance Criteria:**
- [ ] Implement rule: if total `zones_minutes` > 0, `training_before_meal` is required
- [ ] Rule is evaluated after zone normalization/parsing
- [ ] Error message identifies the missing dependent field
- [ ] Unit tests cover `0 minutes` (allowed missing field) and `>0 minutes` (required field)
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-003: Normalize and validate training zones input
**Description:** As an application service, I want robust zone validation so training data is normalized and deterministic for downstream rules.

**Acceptance Criteria:**
- [ ] Accept subset zone keys within `1..5`; missing zones treated as `0`
- [ ] Accept numeric-string keys and normalize to integer zone keys
- [ ] Reject zone keys outside `1..5`
- [ ] Reject zone minutes `< 0`
- [ ] Reject non-integer minute values
- [ ] Unit tests cover mixed key formats, subset keys, out-of-range keys, and negative values
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-004: Add domain invariant checks for macro targets
**Description:** As a domain service, I want invariant checks for macro targets so impossible nutrition outputs are blocked.

**Acceptance Criteria:**
- [ ] Add domain invariant validator for `MacroTargets`
- [ ] Enforce `protein_g >= 0`, `carbs_g >= 0`, and `fat_g >= 0`
- [ ] Negative fat outcomes map to `DomainRuleError` (not `ValidationError`)
- [ ] Unit tests verify failure type and deterministic error category
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-005: Add domain invariant checks for meal allocation structure
**Description:** As a domain service, I want meal allocation invariants enforced so all plans use canonical six-meal structure.

**Acceptance Criteria:**
- [ ] Add domain invariant validator for `MealAllocation` list shape
- [ ] Enforce exactly six allocations
- [ ] Enforce canonical meal-name coverage (all canonical names exactly once)
- [ ] Enforce canonical meal order
- [ ] Reject duplicates and missing meal names
- [ ] Unit tests cover duplicates, missing meal, wrong count, and out-of-order list
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-006: Add carb reconciliation invariant checks
**Description:** As a domain service, I want exact carb reconciliation validation so periodization and response assembly cannot drift from targets.

**Acceptance Criteria:**
- [ ] Add invariant check that sum of meal `carbs_g` equals top-level `carbs_g` under defined precision policy
- [ ] Use deterministic comparison policy: `abs(sum - target) <= 1e-9` (no time/random behavior)
- [ ] Failure returns `DomainRuleError` with reconciliation context
- [ ] Unit tests cover exact-match and mismatch cases
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-007: Compose validation flow in application orchestration
**Description:** As a maintainer, I want one deterministic validation flow so all callers get consistent rule execution and error mapping.

**Acceptance Criteria:**
- [ ] Application flow order is explicit: schema parse -> semantic input validation -> domain invariant checks
- [ ] Domain invariant functions remain in `domain`; application layer orchestrates calls only
- [ ] Mapping to `ValidationError` and `DomainRuleError` remains stable
- [ ] Unit/integration tests verify flow ordering and failure boundaries
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-008: Expand invalid-input and invariant-failure test matrix
**Description:** As a maintainer, I want matrix tests for Phase 3 rules so regressions are caught quickly and deterministically.

**Acceptance Criteria:**
- [ ] Add parameterized tests for semantic input failures (`age`, `weight`, training dependency)
- [ ] Add parameterized tests for zone normalization and invalid zone scenarios
- [ ] Add parameterized tests for domain invariant failures (negative fat, meal uniqueness/order/count, carb mismatch)
- [ ] Tests assert stable error type/category rather than brittle full-message snapshots
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-009: Document validation boundary and error taxonomy
**Description:** As a contributor, I want concise validation-layer documentation so future phases preserve boundaries and behavior.

**Acceptance Criteria:**
- [ ] Update docs to define Phase 3 split: application semantic validation vs domain invariants
- [ ] Document deterministic validation flow and typed error mapping
- [ ] Document zone normalization behavior (subset keys + numeric-string key normalization)
- [ ] Include at least one valid and one invalid payload example with expected error category
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

## 4. Functional Requirements

- FR-1: The system must perform semantic input validation after schema parsing and before calculations.
- FR-2: The system must enforce `age > 0` and `weight_kg > 0` as deterministic semantic checks.
- FR-3: The system must require `training_before_meal` when total training minutes are greater than zero.
- FR-4: The system must accept subset zone keys in `1..5`, normalize numeric-string keys to integer keys, and treat missing keys as zero.
- FR-5: The system must reject zone keys outside `1..5`, negative minutes, and non-integer minute values.
- FR-6: The system must enforce domain macro invariants including non-negative `fat_g`.
- FR-7: The system must enforce six unique canonical meals in canonical order for meal allocations.
- FR-8: The system must enforce carb total reconciliation between top-level and meal-level values using `abs(sum - target) <= 1e-9`.
- FR-9: Semantic input failures must map to `ValidationError`; invariant failures must map to `DomainRuleError`.
- FR-10: Phase 3 validation behavior must be covered by parameterized unit/integration tests.

## 5. Non-Goals (Out of Scope)

- Implementing BMR/TDEE or macro formula engines (Phase 4).
- Implementing training fueling rule computation (Phase 5).
- Implementing periodization allocation engine (Phase 6).
- Implementing meal split output assembly and rounding residual strategy changes (Phase 7).
- CLI UX polish beyond using existing validation/error pathways.

## 6. Design Considerations

- Preserve architecture boundaries from `docs/ARCHITECTURE.md`.
- Keep validators deterministic and pure where possible.
- Keep error messages concise but field-specific for machine and human debugging.

## 7. Technical Considerations

- Use existing pydantic contracts for schema-level parsing; do not duplicate schema validation logic.
- Introduce dedicated validator modules/functions instead of embedding checks in CLI handlers.
- Prefer parameterized tests for invalid matrices to reduce duplication and increase coverage clarity.
- Keep normalization policy explicit and documented for training zone keys and missing zone defaults.

## 8. Success Metrics

- Invalid semantic payloads fail fast before calculation logic is entered.
- Invariant violations produce deterministic `DomainRuleError` failures.
- Test matrix covers all Phase 3 planned rules and passes consistently.
- No regression in existing exit-code mapping for validation and domain errors.

## 9. Open Questions

- Should domain invariant validators run only on assembled response objects, or also on intermediate structures where applicable?

## 10. Implementation Backlog (Phase 3)

1. Create application semantic validator module and wire `age`/`weight` checks.
2. Implement training dependency rule (`training_before_meal` required if total minutes > 0).
3. Implement zone normalization and zone-value semantic validation.
4. Create domain macro invariant validator (`fat_g >= 0` and other non-negative guards).
5. Create domain meal-allocation invariant validator (count, uniqueness, canonical order).
6. Add carb reconciliation invariant check function using `abs(sum - target) <= 1e-9`.
7. Wire orchestrated validation sequence in application service.
8. Add/expand parameterized tests for semantic and invariant matrices.
9. Update docs with validation boundary, taxonomy, and payload examples.
