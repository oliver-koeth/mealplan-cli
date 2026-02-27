# PRD: Phase 1 Foundation and Scaffolding

## 1. Introduction/Overview

Phase 1 establishes the technical foundation for `mealplan` so subsequent domain and CLI features can be implemented safely and consistently.  
This phase focuses on repository structure, packaging/tooling, strict quality gates, a minimal runnable CLI stub, shared error contracts, and baseline CI.

The objective is to deliver a deterministic, enforceable development baseline without implementing nutrition business logic yet.

## 2. Goals

- Create the architecture-aligned source and test directory skeleton.
- Make the project pip-installable and runnable locally via `uv`.
- Establish strict quality gates: lint, typecheck (`mypy --strict`), and tests.
- Provide a minimal `mealplan` CLI command stub that responds to `--help`.
- Define shared typed error hierarchy and canonical exit code mapping.
- Add GitHub Actions CI that runs quality gates on push and pull requests.

## 3. User Stories

### US-001: Create architecture-aligned project skeleton
**Description:** As a developer, I want a standard source and test layout so feature work follows clear module boundaries.

**Acceptance Criteria:**
- [ ] Create `src/mealplan/` with subpackages: `cli`, `application`, `domain`, `infrastructure`, `shared`
- [ ] Create `tests/` with subdirectories: `unit`, `integration`, `cli`, `golden`
- [ ] Add package marker files (`__init__.py`) where needed for imports
- [ ] Add a short README section documenting the directory layout intent
- [ ] `pytest` discovers tests successfully (even with placeholder smoke tests)
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes

### US-002: Add packaging and executable entrypoint
**Description:** As a developer, I want installable packaging and a command entrypoint so the CLI can be invoked consistently.

**Acceptance Criteria:**
- [ ] Create/update `pyproject.toml` with project metadata and dependencies
- [ ] Configure console script entrypoint `mealplan`
- [ ] Project installs in editable mode via `uv`
- [ ] Running `uv run mealplan --help` exits with code `0`
- [ ] Basic dependency lock/update workflow is documented
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-003: Implement minimal runnable CLI stub
**Description:** As a user, I want a minimal working command so I can confirm CLI wiring before business logic is added.

**Acceptance Criteria:**
- [ ] Implement root CLI app with Typer
- [ ] `mealplan --help` shows command help and usage text
- [ ] Command path returns deterministic response for placeholder invocation (no hidden randomness/time state)
- [ ] Stub avoids embedding domain business logic
- [ ] CLI module imports only allowed layers (`application`/`shared`) per architecture intent
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-004: Configure strict quality tooling
**Description:** As a maintainer, I want strict lint/type/test standards so regressions are caught early.

**Acceptance Criteria:**
- [ ] Configure `ruff` rules in project config
- [ ] Configure `mypy --strict` for `src/mealplan`
- [ ] Configure `pytest` defaults and test path discovery
- [ ] Add one command (or Makefile/nox/task alias) to run all quality checks locally
- [ ] Document local quality commands in README
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-005: Define shared error hierarchy and exit codes
**Description:** As a developer, I want typed errors and canonical exit codes so failures are consistent and machine-friendly.

**Acceptance Criteria:**
- [ ] Add shared exceptions: `MealPlanError`, `ValidationError`, `DomainRuleError`, `ConfigError`, `OutputError`
- [ ] Define canonical exit codes: success `0`, validation `2`, domain `3`, infrastructure/runtime `4`
- [ ] Add mapping utility from exception type to exit code
- [ ] Add unit tests for exception-to-exit-code mapping
- [ ] CLI stub uses mapping pathway for controlled error handling
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-006: Scaffold pydantic request/response boundary contracts
**Description:** As a developer, I want boundary contract scaffolding using pydantic so future input/output validation is consistent.

**Acceptance Criteria:**
- [ ] Add pydantic base models for request and response placeholders in application boundary layer
- [ ] Include minimal fields required for stub flow (with TODO markers for Phase 2 model completion)
- [ ] Ensure no business rule validation is implemented beyond basic type shape in this phase
- [ ] Add tests that model parsing/serialization works for placeholder payloads
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-007: Add baseline GitHub Actions CI pipeline
**Description:** As a maintainer, I want CI to run quality checks automatically on push and pull request.

**Acceptance Criteria:**
- [ ] Add GitHub Actions workflow under `.github/workflows/`
- [ ] Workflow triggers on `push` and `pull_request`
- [ ] CI installs project dependencies with `uv`
- [ ] CI runs `ruff check .`, `mypy --strict src`, and `pytest`
- [ ] CI fails fast when any quality gate fails
- [ ] README includes a short section on CI expectations

### US-008: Add developer bootstrap and contribution docs
**Description:** As a new contributor, I want explicit setup and workflow instructions so I can start contributing quickly.

**Acceptance Criteria:**
- [ ] Document local setup steps (Python version, `uv sync`, command usage)
- [ ] Document how to run `mealplan --help`
- [ ] Document required pre-commit quality commands
- [ ] Add contribution notes covering architecture boundary expectations
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

## 4. Functional Requirements

- FR-1: The repository must contain the architecture-defined source and test directory layout.
- FR-2: The package must expose an installable `mealplan` CLI entrypoint.
- FR-3: Executing `mealplan --help` must succeed and return exit code `0`.
- FR-4: The codebase must enforce linting with `ruff`.
- FR-5: The codebase must enforce strict static typing with `mypy --strict` on `src`.
- FR-6: The codebase must include executable tests via `pytest`.
- FR-7: Shared typed exceptions and canonical CLI exit codes must be defined in code.
- FR-8: Exception-to-exit-code mapping must be deterministic and unit-tested.
- FR-9: Boundary contracts must be scaffolded using pydantic models.
- FR-10: A GitHub Actions workflow must run lint, typecheck, and tests on push and PR.
- FR-11: Developer documentation must include setup, run, and quality-check instructions.

## 5. Non-Goals (Out of Scope)

- Implementing energy, macro, training fueling, or periodization algorithms.
- Implementing full CLI argument schema from requirements.
- Implementing final domain enums and full model constraints (Phase 2+).
- Implementing non-JSON output formats or UX enhancements.
- Adding external integrations, persistence, or cloud features.

## 6. Design Considerations

- Keep CLI thin; no nutrition rule logic in command handlers.
- Keep module boundaries aligned with `docs/ARCHITECTURE.md`.
- Prefer explicit, simple structure over premature abstractions in scaffolding.

## 7. Technical Considerations

- Python target: `3.11+`.
- Dependency manager and runner: `uv`.
- CLI framework: `Typer`.
- Validation/contracts direction: `pydantic` (boundary scaffolding only in this phase).
- Tooling baseline: `ruff`, `mypy --strict`, `pytest`.

## 8. Success Metrics

- `uv run mealplan --help` works locally with exit code `0`.
- Local all-check command completes successfully (lint + typecheck + tests).
- CI pipeline executes all quality gates on pull requests.
- New contributors can bootstrap and run checks using documented steps without extra guidance.

## 9. Open Questions

- Should we enforce import-layer boundaries via automated tooling now (for example, import-linter) or defer to code review until Phase 2?
- Should CI test across a Python version matrix now, or keep a single 3.11 job for faster Phase 1 iteration?

