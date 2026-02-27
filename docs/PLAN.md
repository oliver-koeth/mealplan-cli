# Implementation Plan --- `mealplan` CLI

## 1. Goal

Implement `mealplan` in a sequence that minimizes rework, enforces deterministic behavior early, and follows the documented architecture boundaries.

Primary references:
- `docs/REQUIREMENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/MODEL.md`

## 2. Guiding Principles

- Build domain logic before CLI wiring.
- Lock contracts and validation early.
- Keep business rules pure and deterministic.
- Prove correctness with unit and integration tests before UX polish.

## 3. Phased Build Order

## Phase 1: Foundation and Scaffolding

Scope:
- Create project structure from architecture:
  - `src/mealplan/{cli,application,domain,infrastructure,shared}`
  - `tests/{unit,integration,cli,golden}`
- Add packaging/tooling baseline (`pyproject.toml`, lint/type/test config).
- Add shared error hierarchy and canonical CLI exit codes.

Deliverables:
- Runnable project skeleton.
- Baseline CI-ready commands for lint, typecheck, and tests.
- Typed exception classes:
  - `MealPlanError`
  - `ValidationError`
  - `DomainRuleError`
  - `ConfigError`
  - `OutputError`

Completion criteria:
- Project installs and test runner executes.
- Import boundaries are enforceable by structure and conventions.

## Phase 2: Canonical Contracts (Models and DTOs)

Scope:
- Implement enums and value definitions from `MODEL.md`:
  - `Gender`, `ActivityLevel`, `CarbMode`, `TrainingLoadTomorrow`, `MealName`
- Implement request and response contracts aligned with requirements output.
- Centralize canonical meal ordering and units policy.

Deliverables:
- Domain model module(s) and typed request/response DTOs.
- One shared canonical meal sequence used across calculators and output.

Completion criteria:
- Contracts compile/typecheck.
- Contract tests validate required fields and allowed values.

## Phase 3: Validation Layer

Scope:
- Implement input validation:
  - `age > 0`
  - `weight > 0`
  - valid enums
  - training zone key/value constraints
  - `training-before` required when training minutes exist
- Implement domain invariant checks:
  - fat must be non-negative
  - carb totals reconcile exactly
  - six unique meals in canonical order

Deliverables:
- Validation functions/services with typed errors.
- Unit tests for invalid-input matrix and invariant failures.

Completion criteria:
- Invalid requests fail fast with deterministic error types.

## Phase 4: Core Energy and Macro Engines

Scope:
- Implement BMR/TDEE service with activity multipliers.
- Implement protein/carbs/fat target calculation per carb mode.
- Handle current height ambiguity with documented default behavior.

Deliverables:
- Pure domain services:
  - Energy calculation
  - Macro target calculation
- Unit tests for formulas and edge cases.
- ADR note for height handling in v0.2.

Completion criteria:
- Formula tests pass and negative-fat scenarios are rejected.

## Phase 5: Training Fueling Engine

Scope:
- Implement fueling rule:
  - all training in zone 1 => `0g`
  - any zone 2+ => `total_minutes * 1g`

Deliverables:
- Pure training fueling service and focused tests.

Completion criteria:
- All zone permutation tests pass.

## Phase 6: Periodization Allocation Engine

Scope:
- Implement periodized carb redistribution:
  - two post-training high-carb meals
  - high meal = `30%` of daily carbs each
  - low meals share remainder evenly
- Implement next-day high-load override and conflict handling.
- Enforce precedence exactly as requirements define.

Deliverables:
- Periodization strategy/service module.
- Exhaustive tests for precedence and conflict cases.

Completion criteria:
- Allocation remains deterministic and carb totals reconcile exactly.

## Phase 7: Meal Split and Response Assembly

Scope:
- Assemble six ordered meal entries with macro values.
- Apply deterministic rounding at output boundary.
- Apply deterministic residual adjustment policy when needed.

Deliverables:
- Meal allocation assembler.
- Output DTO population for top-level values and `meals[]`.

Completion criteria:
- Meal totals reconcile with top-level totals under rounding policy.

## Phase 8: Application Orchestration

Scope:
- Implement calculation use case flow:
  - validate -> calculate energy/macros -> training fuel -> periodization -> assemble response
- Keep orchestration stateless and deterministic.

Deliverables:
- `MealPlanCalculationService` (or equivalent).
- Integration tests with representative scenarios.

Completion criteria:
- End-to-end application-layer tests pass without CLI involvement.

## Phase 9: CLI Implementation

Scope:
- Implement `mealplan` command with typed options/flags.
- Parse training zones input, map to request DTO, call application service.
- Add format handling and `--debug` behavior.
- Map exceptions to documented exit codes.

Deliverables:
- CLI command entry point and handlers.
- CLI tests for valid runs and failure modes.

Completion criteria:
- CLI produces stable JSON output and correct exit codes.

## Phase 10: Golden Tests, Packaging, and Release Readiness

Scope:
- Add golden-file regression tests for deterministic outputs.
- Finalize docs/examples and package metadata.
- Verify pip-installable workflow and local invocation.

Deliverables:
- Golden snapshots for critical scenarios.
- Updated usage docs and release checklist.

Completion criteria:
- Determinism proven across repeated runs.
- Project is ready for first usable release build.

## 4. Suggested Milestone Gates

Gate A (Phases 1-3):
- Contracts and validation are stable.
- Safe to begin core calculations.

Gate B (Phases 4-6):
- Domain logic is complete and tested.
- Highest-risk rule complexity is retired.

Gate C (Phases 7-9):
- End-to-end behavior works through CLI.
- User-facing behavior is stable.

Gate D (Phase 10):
- Regression safety net and packaging complete.

## 5. Key Risks and Mitigations

- Height ambiguity in BMR formula:
  - Mitigation: define explicit temporary default and record ADR.
- Rounding drift across meal allocations:
  - Mitigation: deterministic residual adjustment to final canonical meal.
- Periodization precedence regressions:
  - Mitigation: dedicated precedence matrix tests and golden snapshots.
- Boundary leakage (CLI logic in domain):
  - Mitigation: enforce module dependency direction and code review checklist.

## 6. What Not to Build Early

- Additional commands beyond primary calculation flow.
- Non-JSON output polish before deterministic core is complete.
- Integrations, persistence, or cloud-connected features outside current scope.

