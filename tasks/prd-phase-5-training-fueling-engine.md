# PRD: Phase 5 Training Fueling Engine

## 1. Introduction/Overview

Phase 5 adds the dedicated training fueling calculator that determines `training_carbs_g` from normalized training-zone minutes.

This phase implements the fueling rule specified in requirements and model docs:
- all training in zone 1 only => `0g`
- any minutes in zone 2-5 => `total_minutes * 1g` (equivalent to `60g/hour`)

The implementation is intentionally scoped to a pure `domain` service only, with no new application wrapper or CLI wiring in this phase.

## 2. Goals

- Implement a deterministic pure-domain fueling service for `training_carbs_g`.
- Apply rule precedence exactly: `any zone >=2` overrides zone 1 behavior.
- Consume normalized zone input from Phase 3 without duplicating validation in Phase 5.
- Add a medium-depth permutation test matrix covering representative single-zone and mixed-zone cases.
- Enforce strict float output expectations in tests (for example `60.0`, not `60`).

## 3. User Stories

### US-001: Implement pure domain fueling calculator
**Description:** As an application orchestrator, I want a pure domain function for training fueling so later orchestration can call one deterministic entrypoint.

**Acceptance Criteria:**
- [ ] Add domain fueling function that accepts normalized `zones_minutes` for zones `1..5`
- [ ] Function returns `training_carbs_g` as `float`
- [ ] Function has no side effects and no dependency on CLI/application modules
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-002: Implement all-zone-1 fueling rule
**Description:** As a nutrition calculation engine, I want training that occurs only in zone 1 to produce zero fueling carbs so low-intensity sessions are handled per requirements.

**Acceptance Criteria:**
- [ ] If all non-zero minutes are in zone 1, result is exactly `0.0`
- [ ] If total minutes are `0`, result is exactly `0.0`
- [ ] Unit tests assert strict float equality for both cases
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-003: Implement zone-2-plus override rule
**Description:** As a nutrition calculation engine, I want any zone 2-5 minutes to trigger fueling based on total duration so moderate/high intensity sessions are fueled consistently.

**Acceptance Criteria:**
- [ ] If any zone `2..5` has minutes `> 0`, result uses `sum(all zone minutes) * 1.0`
- [ ] Zone 1 minutes are included in total duration once override is triggered
- [ ] Unit tests verify representative zone 2, 3, 4, and 5 presence scenarios
- [ ] Unit tests assert strict float outputs (for example `30.0`, `60.0`, `95.0`)
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-004: Enforce deterministic precedence behavior
**Description:** As a maintainer, I want explicit precedence tests so regressions cannot invert the `all-Z1` vs `any-Z2+` behavior.

**Acceptance Criteria:**
- [ ] Tests include mixed sessions with zone 1 plus zone `2..5` minutes and confirm override path
- [ ] Tests include boundary sessions with only zone 1 minutes and confirm zero path
- [ ] Tests document precedence intent in case names
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-005: Keep validation boundary from Phase 3
**Description:** As an architect, I want fueling logic to trust Phase 3 normalization/validation so boundaries remain clean and rules are not duplicated.

**Acceptance Criteria:**
- [ ] Phase 5 service assumes normalized zone keys/values from Phase 3
- [ ] No duplicate validation for out-of-range zone keys or negative minutes is added in Phase 5
- [ ] Tests use normalized valid zone payloads only
- [ ] Module/docs notes clarify that malformed input rejection remains a Phase 3 concern
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-006: Add medium-depth permutation test matrix
**Description:** As a maintainer, I want a representative matrix of single-zone and mixed-zone cases so fueling rule behavior is proven without full combinatorial explosion.

**Acceptance Criteria:**
- [ ] Add parameterized tests for:
  - only zone 1 active
  - only one zone in `2..5` active
  - mixed zone 1 + zone `2..5`
  - multiple zones in `2..5`
  - all zeros
- [ ] Test matrix size is medium-depth (representative, not exhaustive combinations)
- [ ] Expected values are explicit strict floats in each case
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-007: Expose stable interface for later orchestration
**Description:** As a Phase 8 implementer, I want a stable domain API contract for fueling so orchestration can integrate without refactoring this phase’s core logic.

**Acceptance Criteria:**
- [ ] Fueling function name/signature is clear and typed for direct use by orchestration
- [ ] Return semantics are documented: always `float`, deterministic for same input
- [ ] No Phase 5 application wrapper is introduced
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

## 4. Functional Requirements

- FR-1: The system must compute `training_carbs_g` from normalized `zones_minutes` (zones `1..5`) as pure domain logic.
- FR-2: The system must return `0.0` when all non-zero training minutes are in zone 1 only.
- FR-3: The system must return `0.0` when total training minutes are `0`.
- FR-4: The system must return `sum(zones_minutes.values()) * 1.0` when any zone in `2..5` has minutes `> 0`.
- FR-5: The system must enforce precedence where the zone-2-plus rule overrides zone-1-only behavior.
- FR-6: The system must return `training_carbs_g` as `float` and preserve deterministic results.
- FR-7: Phase 5 must trust Phase 3-normalized/validated input and must not duplicate semantic validation rules.
- FR-8: Fueling behavior must be covered by a representative medium-depth parameterized unit test matrix.
- FR-9: Test assertions for `training_carbs_g` must use strict float expectations.
- FR-10: Phase 5 output remains a standalone fueling value and does not alter meal carb allocation behavior.

## 5. Non-Goals (Out of Scope)

- Adding an application-layer wrapper or orchestration integration in this phase.
- CLI wiring changes for fueling behavior.
- Re-validating malformed training-zone payloads already handled by Phase 3.
- Implementing periodized meal carb redistribution and precedence conflicts (Phase 6).
- Implementing meal split assembly or output rounding policy changes (Phase 7).

## 6. Design Considerations

- Keep the fueling calculator small and explicit so rule precedence is obvious from code.
- Name constants and helper logic clearly to avoid ambiguity between intensity detection and duration summing.
- Preserve deterministic behavior by avoiding hidden defaults, external state, or context-dependent behavior.

## 7. Technical Considerations

- Implementation belongs in `domain` module(s), consistent with architecture boundaries.
- Input contract is normalized zone minutes from Phase 3 (`dict[int, int]` for zones `1..5`).
- Use parameterized unit tests to cover representative permutations with minimal duplication.
- Keep this phase independent from periodization logic so later precedence work remains isolated.

## 8. Success Metrics

- Fueling service returns expected strict-float outputs for all planned representative scenarios.
- Precedence behavior (`any zone 2+` override) is explicitly covered and stable in tests.
- No duplicated validation logic is introduced in domain fueling service.
- Test suite catches fueling regressions quickly via parameterized cases.

## 9. Open Questions

- None for Phase 5 scope after clarification decisions (`domain-only`, normalized-input trust, medium matrix, strict-float assertions).

## 10. Implementation Backlog (Phase 5)

1. Add domain fueling service module/function for training-carb calculation.
2. Implement zero-fueling branch for all-zone-1-only and total-zero scenarios.
3. Implement zone-2-plus override branch using total training duration in all zones.
4. Ensure return type is explicit `float` for all paths.
5. Add representative parameterized unit tests for single-zone and mixed-zone scenarios.
6. Add explicit precedence-focused tests (zone 1 only vs zone 1 + zone 2+).
7. Add/adjust module documentation notes preserving Phase 3 validation boundary.
8. Run `ruff check .`, `mypy --strict src`, and `pytest` to confirm readiness.
