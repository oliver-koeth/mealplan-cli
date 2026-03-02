# PRD: Phase 4 Core Energy and Macro Engines

## 1. Introduction/Overview

Phase 4 implements the first production nutrition-calculation engines in `domain`: energy (`BMR`/`TDEE`) and macro targets (`protein_g`, `carbs_g`, `fat_g`).

This phase converts the locked contracts and validation foundations from Phases 2-3 into deterministic formula services that later phases (training fueling, periodization, meal assembly) can compose.

## 2. Goals

- Implement deterministic BMR/TDEE calculation using Mifflin-St Jeor + activity multipliers.
- Implement deterministic macro target calculation for all carb modes (`low`, `normal`, `periodized` baseline).
- Enforce negative-fat rejection as a hard domain rule.
- Keep formula services pure and side-effect free.
- Consume required `height_cm` input (`int > 0`) for all energy calculations.

## 3. User Stories

### US-001: Implement activity multiplier mapping
**Description:** As a domain calculator, I want one canonical activity-factor mapping so TDEE results are consistent across all callers.

**Acceptance Criteria:**
- [ ] Add canonical mapping: `low -> 1.2`, `medium -> 1.375`, `high -> 1.55`
- [ ] Mapping uses existing `ActivityLevel` enum values only
- [ ] Mapping is colocated with energy calculation logic (no duplication across modules)
- [ ] Unit tests verify each enum maps to the expected numeric factor
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-002: Implement BMR calculation with gender-specific formulas
**Description:** As a domain calculator, I want BMR calculated by Mifflin-St Jeor so energy output follows requirements and model specifications.

**Acceptance Criteria:**
- [ ] Implement formulas:
  - `male: BMR = 10*weight_kg + 6.25*height_cm - 5*age + 5`
  - `female: BMR = 10*weight_kg + 6.25*height_cm - 5*age - 161`
- [ ] Formula selection is based only on canonical `Gender` enum
- [ ] Function is deterministic and pure (no hidden state, no time/random dependency)
- [ ] Unit tests verify male/female outputs with fixed fixture inputs
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-003: Implement TDEE calculation from BMR and activity level
**Description:** As an application service, I want TDEE derived from BMR and activity factor so downstream macro calculations have a stable calorie input.

**Acceptance Criteria:**
- [ ] Implement `TDEE = BMR * activity_factor`
- [ ] TDEE output is `float` and remains unrounded internally
- [ ] Function accepts typed profile input and returns deterministic value
- [ ] Unit tests verify TDEE for all three activity levels from the same BMR baseline
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-004: Use required height input in energy calculation contracts
**Description:** As a maintainer, I want energy formulas to consume explicit `height_cm` input so BMR/TDEE no longer depend on fallback behavior.

**Acceptance Criteria:**
- [ ] Energy service signature requires `height_cm` from typed profile/request contracts
- [ ] No fallback/default-height code path exists in Phase 4 domain services
- [ ] Validation contract for `height_cm` is documented as integer `> 0`
- [ ] Height specification is explicit: no upper bound and no numeric-string coercion
- [ ] Unit tests verify BMR/TDEE with explicit height inputs for both genders
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-005: Implement macro target calculator for protein and carbs by mode
**Description:** As a domain calculator, I want macro targets derived from bodyweight and carb mode so output contracts can be filled consistently.

**Acceptance Criteria:**
- [ ] Implement protein formula: `protein_g = 2 * weight_kg`
- [ ] Implement carb-mode formulas:
  - `low: carbs_g = 3 * weight_kg`
  - `normal: carbs_g = 5 * weight_kg`
  - `periodized: carbs_g = 4 * weight_kg` (baseline before redistribution)
- [ ] Calculator consumes canonical `CarbMode` enum only
- [ ] Unit tests verify expected outputs for each carb mode and fixed weight fixtures
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-006: Implement fat-as-residual calculation with negative-fat rejection
**Description:** As a domain calculator, I want fat computed from remaining calories and rejected when negative so impossible macro states cannot propagate.

**Acceptance Criteria:**
- [ ] Implement residual formulas:
  - `fat_kcal = tdee_kcal - (protein_g * 4) - (carbs_g * 4)`
  - `fat_g = fat_kcal / 9`
- [ ] Reject when `fat_g < 0` with deterministic `DomainRuleError`
- [ ] Error category remains stable for CLI exit-code mapping compatibility
- [ ] Unit tests cover positive fat and negative-fat rejection cases
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-007: Provide composed domain API for Phase 4 calculations
**Description:** As an application orchestrator, I want a simple typed entrypoint for energy + macro calculations so Phase 8 orchestration can integrate without formula duplication.

**Acceptance Criteria:**
- [ ] Expose typed domain service functions for:
  - energy calculation (`tdee_kcal`)
  - macro target calculation (`MacroTargets`)
- [ ] Service boundaries keep formulas in `domain`, not CLI/application parsing modules
- [ ] Service signatures align with existing Phase 2 contracts and Phase 3 validation outputs
- [ ] Unit tests verify composed usage and return types
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-008: Add formula and edge-case test matrix
**Description:** As a maintainer, I want a focused matrix of formula and boundary tests so regressions in numeric logic are caught immediately.

**Acceptance Criteria:**
- [ ] Add parameterized tests for BMR and TDEE scenarios across genders and activity levels
- [ ] Add parameterized tests for carb mode outputs (`low`, `normal`, `periodized`)
- [ ] Add tests for fat residual exactness and negative-fat rejection
- [ ] Tests assert deterministic error type/category, not brittle full-message snapshots
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-009: Align tests and docs with required height input
**Description:** As a contributor, I want Phase 4 tests and documentation to use required height so formula behavior is unambiguous.

**Acceptance Criteria:**
- [ ] Unit fixtures for energy formulas include explicit `height_cm` values
- [ ] Test names and assertions no longer reference default-height behavior
- [ ] Phase 4 docs reference required `height_cm` input and integer `> 0` validation
- [ ] Removed/updated references to temporary height ADR from this phase backlog
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

## 4. Functional Requirements

- FR-1: The system must compute BMR using Mifflin-St Jeor formulas by `Gender`.
- FR-2: The system must compute TDEE as `BMR * activity_factor` using canonical factors (`1.2`, `1.375`, `1.55`).
- FR-3: The system must require `height_cm` input for energy calculations, with validation rule strict integer `> 0` and no upper bound.
- FR-4: The system must compute `protein_g = 2 * weight_kg`.
- FR-5: The system must compute carbs by `CarbMode` (`3`, `5`, `4` g/kg for low, normal, periodized baseline respectively).
- FR-6: The system must compute `fat_g` as calorie residual from TDEE after protein/carbs calories.
- FR-7: The system must reject `fat_g < 0` with deterministic `DomainRuleError`.
- FR-8: Phase 4 services must remain pure domain logic with no CLI parsing concerns.
- FR-9: Phase 4 numeric behavior must be covered by parameterized unit tests.
- FR-10: Phase 4 artifacts must not rely on temporary/default height behavior.

## 5. Non-Goals (Out of Scope)

- Implementing training fueling logic (`training_carbs_g`) from Phase 5.
- Implementing periodized meal-level carb redistribution from Phase 6.
- Implementing six-meal macro split assembly and rounding residual placement from Phase 7.
- Implementing Phase 8 end-to-end orchestration flow.
- CLI UX enhancements beyond introducing required `--height` support.

## 6. Design Considerations

- Keep formula constants centralized and explicitly named.
- Prefer small pure functions over monolithic calculators to simplify testing.
- Preserve deterministic behavior by requiring explicit inputs (including `height_cm`) and avoiding hidden defaults.

## 7. Technical Considerations

- Reuse existing domain enums and DTO types from Phase 2.
- Keep strict layer boundaries: `cli -> application -> domain`.
- Do not round intermediate formula outputs in domain services.
- Ensure error mapping remains compatible with existing shared error/exit-code contracts.

## 8. Success Metrics

- Formula test suite covers BMR/TDEE, carb modes, and fat residual cases and passes consistently.
- Negative-fat scenarios fail fast with deterministic `DomainRuleError`.
- No duplication of energy/macro formulas across modules.
- Height input is required and validated as integer `> 0` across contracts and tests.

## 9. Open Questions

- Should Phase 4 include explicit tolerance policy for floating-point assertions, or defer to later output-boundary rounding work?

## 10. Implementation Backlog (Phase 4)

1. Add canonical activity-factor mapping in domain energy module.
2. Implement gender-specific BMR function.
3. Implement TDEE computation from BMR and activity factor.
4. Wire required `height_cm` input into energy service signatures and fixtures.
5. Implement macro calculator: protein formula + carb-mode formulas.
6. Implement residual fat calculation and `fat_g < 0` rejection via `DomainRuleError`.
7. Expose typed domain service entrypoints for energy + macro targets.
8. Add parameterized unit test matrix for formulas and edge cases.
9. Update Phase 4 docs/tests to remove temporary-height assumptions.
