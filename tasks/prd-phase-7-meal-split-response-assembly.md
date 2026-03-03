# PRD: Phase 7 Meal Split and Response Assembly

## 1. Introduction/Overview

Phase 7 assembles the final six-meal macro output structure and top-level response payload from previously computed domain values.

This phase introduces a domain-only meal assembly pathway that:
- builds six ordered `MealAllocation` entries
- applies deterministic output-boundary rounding
- applies deterministic residual adjustment when rounding drift occurs
- populates response DTO-compatible top-level fields and `meals[]`

## 2. Goals

- Implement deterministic six-meal assembly in canonical order.
- Split protein and fat equally across all six meals.
- Reuse Phase 6 carb allocation output for meal-level carbs.
- Apply two-decimal rounding at output boundary only.
- Apply deterministic residual adjustment to always-canonical last meal (`evening-snack`).
- Ensure meal-level totals reconcile to top-level targets after rounding policy.
- Keep Phase 7 as domain-only assembly (no Phase 8 orchestration wiring in this phase).

## 3. User Stories

### US-001: Implement domain-only meal assembler API
**Description:** As a future orchestrator, I want one domain assembly entrypoint so output construction logic is centralized and deterministic.

**Acceptance Criteria:**
- [ ] Add canonical Phase 7 assembler API in `src/mealplan/domain/services.py`.
- [ ] API is domain-only with no application orchestration wiring in Phase 7.
- [ ] API returns six meal entries in canonical order suitable for response population.
- [ ] Assembler API is exported via `src/mealplan/domain/__init__.py`.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-002: Assemble six canonical meal entries
**Description:** As a consumer of meal outputs, I want exactly six ordered meals so response structure is stable and deterministic.

**Acceptance Criteria:**
- [ ] Assembler output includes exactly six entries.
- [ ] Meal names are canonical and ordered: breakfast, morning-snack, lunch, afternoon-snack, dinner, evening-snack.
- [ ] No duplicate or missing meal names are allowed.
- [ ] Tests assert exact ordering and uniqueness.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-003: Split protein and fat equally across all meals
**Description:** As a deterministic rules engine, I want protein and fat distributed evenly so Phase 7 can assemble complete meal macros without introducing new prioritization rules.

**Acceptance Criteria:**
- [ ] Protein split is equal across six meals from top-level `protein_g`.
- [ ] Fat split is equal across six meals from top-level `fat_g`.
- [ ] Split uses pre-rounding float arithmetic; no early rounding before boundary step.
- [ ] Tests verify equal distribution behavior before rounding adjustments.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-004: Populate meal carbs from periodization allocation
**Description:** As a meal assembler, I want per-meal carbs sourced from canonical carb allocation so Phase 6 and Phase 7 remain composable.

**Acceptance Criteria:**
- [ ] Carbs per meal are read from canonical allocation map keyed by `MealName`.
- [ ] Assembler enforces complete carb map coverage across all six canonical meals.
- [ ] Missing carb allocation keys produce deterministic domain failure.
- [ ] Tests verify carb carry-through from allocation to meal entries.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-005: Apply two-decimal boundary rounding
**Description:** As an output consumer, I want stable two-decimal meal values so serialized responses are predictable and human-readable.

**Acceptance Criteria:**
- [ ] Round each meal macro field (`carbs_g`, `protein_g`, `fat_g`) to 2 decimals at boundary step.
- [ ] No intermediate calculation function introduces early rounding.
- [ ] Top-level macro values remain canonical inputs and are not re-derived from rounded meal rows.
- [ ] Tests verify deterministic two-decimal outputs for representative fractional scenarios.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-006: Apply deterministic residual adjustment to evening-snack
**Description:** As a reconciliation guard, I want rounding drift corrected in one fixed location so output sums remain deterministic across runs.

**Acceptance Criteria:**
- [ ] If rounded meal totals drift from top-level targets, apply residual adjustment to `evening-snack` only.
- [ ] Residual policy is deterministic and independent of input order or hash-map iteration.
- [ ] Adjustment is applied per macro dimension as needed (`carbs_g`, `protein_g`, `fat_g`).
- [ ] Tests verify drift correction and fixed-target placement at `evening-snack`.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-007: Build response assembly helper for top-level + meals payload
**Description:** As a caller, I want one helper to produce DTO-compatible response shape so Phase 8 integration is mechanical.

**Acceptance Criteria:**
- [ ] Add helper that assembles top-level fields (`TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`) plus `meals[]`.
- [ ] `meals[]` entries use `MealAllocation`-compatible field names and types.
- [ ] Helper output shape aligns with `MealPlanResponse` contract expectations.
- [ ] Tests validate shape and field presence for representative payloads.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-008: Add reconciliation tests under rounding policy
**Description:** As a maintainer, I want explicit rounding/reconciliation tests so regressions in sum integrity are caught immediately.

**Acceptance Criteria:**
- [ ] Add tests where rounded meal sums already match top-level targets (no adjustment path).
- [ ] Add tests where rounded meal sums drift and residual correction is required.
- [ ] Assertions verify post-adjustment equality between rounded meal sums and top-level totals.
- [ ] Tests cover all three macro dimensions (`carbs_g`, `protein_g`, `fat_g`).
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-009: Document Phase 7 assembly and rounding contracts
**Description:** As a contributor, I want clear Phase 7 assembly/rounding docs so later orchestration and CLI phases do not duplicate or conflict with these rules.

**Acceptance Criteria:**
- [ ] Update `docs/ARCHITECTURE.md` with Phase 7 technical boundary and deterministic residual policy.
- [ ] Update `docs/REQUIREMENTS.md` with functional output-rounding and residual adjustment clarifications.
- [ ] Update `docs/MODEL.md` with Phase 7 meal assembly contract details and two-decimal boundary policy.
- [ ] Docs explicitly state residual target meal is always canonical last meal (`evening-snack`).
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

## 4. Functional Requirements

- FR-1: The system must provide a domain-only meal assembly API in `domain` for Phase 7.
- FR-2: The system must produce exactly six `MealAllocation` entries in canonical meal order.
- FR-3: The system must source meal carbs from the canonical carb allocation map.
- FR-4: The system must split `protein_g` equally across six meals before boundary rounding.
- FR-5: The system must split `fat_g` equally across six meals before boundary rounding.
- FR-6: The system must round meal macro outputs to 2 decimals at output boundary only.
- FR-7: The system must apply deterministic residual adjustment to `evening-snack` when rounding drift exists.
- FR-8: The system must reconcile meal totals with top-level `carbs_g`, `protein_g`, and `fat_g` after rounding policy.
- FR-9: The system must produce response DTO-compatible top-level fields and `meals[]` shape.
- FR-10: Phase 7 implementation must not include Phase 8 orchestration wiring.

## 5. Non-Goals (Out of Scope)

- Phase 8 orchestration flow implementation (`validate -> calculate -> fuel -> periodize -> assemble`).
- Phase 9 CLI parsing/output wiring and exception-to-exit-code mapping changes.
- Changes to Phase 6 periodization precedence rules.
- Alternative macro split strategies beyond Phase 7 equal protein/fat distribution.
- Any persistence, external integrations, or non-deterministic output behavior.

## 6. Design Considerations

- Keep assembly and rounding responsibilities centralized to avoid split logic across layers.
- Keep deterministic policies explicit in function names/tests (boundary rounding + fixed residual target meal).
- Preserve canonical ordering through every assembly step to simplify downstream serialization guarantees.

## 7. Technical Considerations

- Reuse `MealName`, canonical meal order constants, and existing domain dataclasses/contracts.
- Keep floating-point calculations unrounded until dedicated boundary-rounding step.
- Preserve deterministic error categories for missing/invalid allocation shapes.
- Prefer parameterized tests for rounding and residual edge matrices.

## 8. Success Metrics

- Assembler always returns six canonical ordered meals with complete macro fields.
- Rounded meal totals reconcile exactly to top-level macro targets via fixed residual policy.
- Repeated runs with identical inputs yield identical meal-level outputs.
- Phase 7 changes remain domain-bound without orchestration/CLI leakage.

## 9. Open Questions

- None for Phase 7 scope after clarification decisions (equal protein/fat split, 2-decimal boundary rounding, residual on `evening-snack`, domain-only boundary).

## 10. Implementation Backlog (Phase 7)

1. Add domain-only Phase 7 assembler API in `src/mealplan/domain/services.py` and export via `mealplan.domain`.
2. Implement canonical six-meal row assembly using `MealName` order and complete carb-map coverage checks.
3. Implement equal pre-round split logic for `protein_g` and `fat_g` across six meals.
4. Add boundary rounding step to 2 decimals for each meal macro field.
5. Implement deterministic residual adjustment policy that always targets `evening-snack`.
6. Add response-shape helper for top-level fields + `meals[]` DTO-compatible payload.
7. Add rounding/reconciliation tests for no-drift and drift-correction paths across carbs/protein/fat.
8. Add validation/error tests for missing carb-map keys and malformed meal assembly inputs.
9. Update `docs/ARCHITECTURE.md`, `docs/REQUIREMENTS.md`, and `docs/MODEL.md` for Phase 7 contracts.
10. Run `ruff check .`, `mypy --strict src`, and `pytest`.
