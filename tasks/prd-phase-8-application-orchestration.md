# PRD: Phase 8 Application Orchestration

## 1. Introduction/Overview

Phase 8 implements the application-layer orchestration flow that composes completed domain services into one deterministic calculation use case.

This phase introduces `MealPlanCalculationService` (or equivalent) that runs the end-to-end application pipeline without CLI wiring:
- validate
- calculate energy/macros
- calculate training fuel
- calculate periodized carb allocation
- assemble final response

The orchestration remains stateless, deterministic, and contract-safe by returning a validated `MealPlanResponse` model.

## 2. Goals

- Implement a single stateless application service for end-to-end calculation flow.
- Enforce fail-fast validation at pipeline start via canonical validation flow.
- Return `MealPlanResponse` model instances (not plain dicts).
- Treat omitted `training_session` (`None`) as zero-training defaults.
- Keep orchestration independent from CLI concerns.
- Add representative application-layer integration tests for happy and failure paths.

## 3. User Stories

### US-001: Add `MealPlanCalculationService` orchestration entrypoint
**Description:** As an application caller, I want one deterministic service API so all calculation stages execute through a single use-case boundary.

**Acceptance Criteria:**
- [ ] Add `MealPlanCalculationService` (or equivalent) in `src/mealplan/application/orchestration.py`.
- [ ] Service method accepts request payload/DTO and returns `MealPlanResponse`.
- [ ] Service has no mutable state and is deterministic for identical inputs.
- [ ] Public application API is documented and type-annotated.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-002: Enforce validation-first fail-fast execution
**Description:** As a maintainer, I want validation run first so invalid requests fail before domain calculations begin.

**Acceptance Criteria:**
- [ ] Orchestration calls canonical validation flow first (`validate_meal_plan_flow`).
- [ ] Validation failure stops pipeline before energy/macro/fueling/periodization/assembly calls.
- [ ] Error typing remains deterministic (`ValidationError`/`DomainRuleError`) for existing exit-code mapping.
- [ ] Tests verify fail-fast ordering behavior.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-003: Wire energy and macro stage composition
**Description:** As an application service, I want to call Phase 4 domain services in order so top-level macro targets are produced deterministically.

**Acceptance Criteria:**
- [ ] Build typed `UserProfile` from validated request.
- [ ] Call `calculate_tdee_kcal` and `calculate_macro_targets` with canonical arguments.
- [ ] Preserve unrounded domain values until Phase 7 assembly boundary.
- [ ] Tests verify stage outputs are passed correctly to downstream stages.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-004: Wire training fuel stage composition
**Description:** As an application service, I want to call Phase 5 fueling from normalized training input so training carbs are integrated into response output.

**Acceptance Criteria:**
- [ ] Convert validated/normalized training session into canonical zones mapping for fueling call.
- [ ] Call `calculate_training_carbs_g` exactly once per request.
- [ ] Training fuel stage remains deterministic and side-effect free.
- [ ] Tests cover zero-training and mixed-zone representative inputs.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-005: Treat `training_session=None` as zero-training defaults
**Description:** As a caller, I want omitted training session to be interpreted consistently so requests without training data still produce deterministic results.

**Acceptance Criteria:**
- [ ] If `training_session` is `None`, orchestration uses zero-training defaults:
  - zones `{1:0,2:0,3:0,4:0,5:0}`
  - `training_before_meal=None`
- [ ] Pipeline proceeds without validation failure for omitted training session.
- [ ] Resulting `training_carbs_g` is `0.0`.
- [ ] Integration tests verify omitted training session behavior in representative scenarios.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-006: Wire periodization stage composition
**Description:** As an application service, I want to call Phase 6 periodization allocator so meal-level carb distribution is derived from top-level carb targets and training context.

**Acceptance Criteria:**
- [ ] Call `calculate_periodized_carb_allocation` with canonical arguments:
  `carb_mode`, `daily_carbs_g`, `training_before_meal`, `training_load_tomorrow`.
- [ ] Preserve Phase 6 precedence/override behavior without duplicating rules in application layer.
- [ ] Tests verify representative periodized and non-periodized flows.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-007: Wire meal split and response assembly stage
**Description:** As an application service, I want to call Phase 7 assembly so final payload shape and rounding policies are applied consistently.

**Acceptance Criteria:**
- [ ] Call `calculate_meal_split_and_response_payload` with canonical top-level values and carb map.
- [ ] Parse/return final result as validated `MealPlanResponse` model instance.
- [ ] No manual response dict mutation outside canonical assembly path.
- [ ] Tests verify returned object type is `MealPlanResponse`.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-008: Add representative application integration matrix
**Description:** As a maintainer, I want representative application-layer integration coverage so orchestration regressions are caught without CLI dependency.

**Acceptance Criteria:**
- [ ] Add representative success scenarios:
  - periodized with training
  - non-periodized with training
  - omitted `training_session`
- [ ] Add representative failure scenarios:
  - validation failure
  - domain failure from downstream stage
- [ ] Tests execute application service directly (no CLI invocation).
- [ ] Assertions cover returned `MealPlanResponse` shape and critical top-level/meal invariants.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-009: Document Phase 8 orchestration boundary and flow
**Description:** As a contributor, I want clear docs for orchestration responsibilities so later CLI integration does not leak business logic into command handlers.

**Acceptance Criteria:**
- [ ] Update `docs/ARCHITECTURE.md` with explicit Phase 8 service boundary and stage sequence.
- [ ] Update `docs/REQUIREMENTS.md` with functional orchestration flow notes as needed.
- [ ] Update `docs/MODEL.md` and/or contracts notes to reflect `MealPlanResponse` return contract at application boundary.
- [ ] Docs state `training_session=None` zero-training interpretation.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

## 4. Functional Requirements

- FR-1: The system must provide a stateless `MealPlanCalculationService` (or equivalent) in the application layer.
- FR-2: Orchestration must execute in fixed order: validate -> energy/macros -> training fuel -> periodization -> assembly.
- FR-3: Orchestration must run canonical validation first and fail fast on validation errors.
- FR-4: Service must return `MealPlanResponse` model instances, not plain dict outputs.
- FR-5: If `training_session` is omitted, orchestration must apply zero-training defaults and continue.
- FR-6: Orchestration must delegate business rules to domain services and not duplicate rule logic in application layer.
- FR-7: End-to-end application behavior must remain deterministic for identical inputs.
- FR-8: Phase 8 integration tests must run without CLI involvement and cover representative success/failure paths.
- FR-9: Error typing from validation/domain failures must remain stable for existing exit-code mapping compatibility.
- FR-10: Phase 8 must not implement Phase 9 CLI parsing/rendering behavior.

## 5. Non-Goals (Out of Scope)

- CLI command option parsing, output formatting flags, and `--debug` behavior (Phase 9).
- Golden snapshot suite and release packaging work (Phase 10).
- Changes to underlying domain formula/periodization/assembly rules already implemented in Phases 4-7.
- New persistence, background jobs, or network integrations.
- UX-facing concerns outside application-layer orchestration.

## 6. Design Considerations

- Keep orchestration as thin composition logic over domain services.
- Make stage boundaries explicit and testable with deterministic fixtures.
- Prefer typed DTO/model transitions over untyped dict mutation in application flow.

## 7. Technical Considerations

- Reuse existing contracts (`MealPlanRequest`, `MealPlanResponse`) and canonical validators.
- Preserve module dependency direction: `application` may call `domain`, not vice versa.
- Keep orchestration free of CLI-specific parsing or formatting logic.
- Integration tests should target `src/mealplan/application/orchestration.py` service API directly.

## 8. Success Metrics

- `MealPlanCalculationService` consistently returns valid `MealPlanResponse` for representative valid inputs.
- Validation failures fail fast before domain calculations.
- Omitted `training_session` requests produce deterministic zero-training behavior.
- Representative application-layer integration matrix passes consistently without CLI execution.

## 9. Open Questions

- None for Phase 8 scope after clarification decisions (`MealPlanResponse` return type, `training_session=None` default handling, representative integration depth, validation-first fail-fast).

## 10. Implementation Backlog (Phase 8)

1. Add `MealPlanCalculationService` (or equivalent) entrypoint in `src/mealplan/application/orchestration.py`.
2. Wire validation-first stage using canonical application validation flow.
3. Build typed `UserProfile` input and call Phase 4 domain services for energy/macros.
4. Normalize training session defaults when omitted and call Phase 5 fueling.
5. Call Phase 6 periodization allocator with canonical arguments.
6. Call Phase 7 assembler and parse/return `MealPlanResponse` model.
7. Add representative integration tests for success paths and fail-fast failure paths (no CLI).
8. Add tests asserting `training_session=None` zero-training behavior.
9. Update architecture/requirements/model docs for Phase 8 orchestration boundary.
10. Run `ruff check .`, `mypy --strict src`, and `pytest`.
