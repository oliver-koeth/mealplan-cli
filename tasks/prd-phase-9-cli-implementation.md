# PRD: Phase 9 CLI Implementation

## 1. Introduction/Overview

Phase 9 implements the production CLI interface for `mealplan` by wiring typed command options to the completed application orchestration service.

This phase adds the full calculation command while preserving the existing `probe` command.  
The CLI must:
- parse typed options/flags
- parse training-zones JSON string input
- call `MealPlanCalculationService`
- support output formats `json|text|table` (default `json`)
- apply `--debug` error behavior
- map exceptions to canonical exit codes

## 2. Goals

- Add full calculation command using typed CLI options and flags.
- Keep CLI thin (no business rules), delegating all logic to application/domain layers.
- Support `--format json|text|table` with deterministic JSON default.
- Implement default concise error output and traceback expansion with `--debug`.
- Enforce strict training-zones parsing from JSON string input only.
- Preserve existing `probe` command while adding production calculation flow.
- Ensure CLI tests cover valid runs and failure-mode exit codes.

## 3. User Stories

### US-001: Add production `mealplan` calculation command
**Description:** As a CLI user, I want a single typed calculation command so I can run meal plan computation end-to-end from terminal inputs.

**Acceptance Criteria:**
- [ ] Add/extend CLI command handler to run production calculation flow.
- [ ] Command options cover required request inputs (`age`, `gender`, `height`, `weight`, `activity`, `carbs`, `training-tomorrow`, training fields).
- [ ] CLI maps parsed args to `MealPlanRequest` payload/DTO expected by application layer.
- [ ] Existing `probe` command remains available and unchanged in behavior.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-002: Implement strict typed flag/option parsing
**Description:** As a maintainer, I want CLI options strongly typed so invalid values fail early with deterministic errors.

**Acceptance Criteria:**
- [ ] Typer option types and enum choices are explicitly enforced.
- [ ] Required options fail with deterministic CLI validation messaging.
- [ ] Optional training fields are parsed without business-rule duplication in CLI.
- [ ] Tests verify typed parsing failures for representative invalid inputs.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-003: Parse `--training-zones` as JSON string only
**Description:** As a CLI user, I want predictable training-zones input behavior so orchestration receives canonical structured data.

**Acceptance Criteria:**
- [ ] `--training-zones` accepts JSON string input only.
- [ ] Invalid JSON is rejected deterministically and mapped through `ValidationError` path.
- [ ] CLI does not support file-path or shorthand parsing forms in Phase 9.
- [ ] Parsed zones structure is passed as request payload field without CLI business logic.
- [ ] Tests verify valid JSON parsing and invalid-JSON rejection.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-004: Wire CLI to `MealPlanCalculationService`
**Description:** As an implementation owner, I want CLI handlers to call the application service directly so CLI remains a thin boundary adapter.

**Acceptance Criteria:**
- [ ] CLI instantiates/calls `MealPlanCalculationService.calculate(...)`.
- [ ] CLI does not directly invoke domain calculators/services.
- [ ] Returned `MealPlanResponse` is used as the single source for output formatting.
- [ ] Tests verify command path calls application service and returns deterministic output.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-005: Implement `--format json|text|table`
**Description:** As a CLI user, I want multiple output formats so I can use machine-readable output by default and human-readable output when needed.

**Acceptance Criteria:**
- [ ] Add `--format` option with allowed values: `json`, `text`, `table`.
- [ ] Default output format is `json`.
- [ ] JSON output stays stable and deterministic for automation use.
- [ ] Text/table output are derived from `MealPlanResponse` without modifying core response values.
- [ ] Tests verify format selection behavior and default JSON output.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-006: Implement `--debug` error behavior
**Description:** As a CLI user, I want concise errors by default and deeper diagnostics when requested so troubleshooting is possible without noisy normal output.

**Acceptance Criteria:**
- [ ] Default error output is concise and user-facing (single-line style).
- [ ] With `--debug`, include traceback/details for the same error.
- [ ] Debug mode does not change successful command output semantics.
- [ ] Tests verify default vs debug error-output differences.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-007: Map exceptions to canonical exit codes
**Description:** As an integration user, I want stable process exit codes so automation can handle failures deterministically.

**Acceptance Criteria:**
- [ ] CLI maps `ValidationError` -> `ExitCode.VALIDATION` (`2`).
- [ ] CLI maps `DomainRuleError` -> `ExitCode.DOMAIN` (`3`).
- [ ] CLI maps unknown/runtime errors -> `ExitCode.RUNTIME` (`4`).
- [ ] Success path exits with `ExitCode.OK` (`0`).
- [ ] Tests verify each mapped code via representative failure scenarios.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-008: Add CLI integration test matrix for valid and failure modes
**Description:** As a maintainer, I want CLI-level end-to-end coverage so regressions in command wiring, formatting, and exit behavior are caught quickly.

**Acceptance Criteria:**
- [ ] Add representative success tests for:
  - default JSON output
  - explicit text format
  - explicit table format
- [ ] Add representative failure tests for:
  - invalid typed flag value
  - invalid training-zones JSON
  - propagated validation/domain/runtime errors with exit code checks
- [ ] Add tests for `--debug` traceback behavior on errors.
- [ ] Tests run through CLI command invocation path (Typer runner/subprocess), not direct service call.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-009: Document Phase 9 CLI contract and usage
**Description:** As a contributor, I want clear CLI docs for flags, formats, debug behavior, and exit codes so users and future phases rely on stable command behavior.

**Acceptance Criteria:**
- [ ] Update `docs/ARCHITECTURE.md` with finalized CLI boundary responsibilities and error/format handling notes.
- [ ] Update `docs/REQUIREMENTS.md` with CLI usage clarifications (`--format`, `--debug`, strict JSON training-zones input).
- [ ] Update README or usage docs with concrete command examples for json/text/table outputs.
- [ ] Document exit-code mapping and debug behavior expectations.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

## 4. Functional Requirements

- FR-1: The system must provide a production `mealplan` calculation CLI command with typed options/flags.
- FR-2: The CLI must parse `--training-zones` as JSON string only and reject invalid JSON deterministically.
- FR-3: The CLI must call `MealPlanCalculationService.calculate(...)` as the application boundary.
- FR-4: The CLI must support `--format json|text|table` with `json` as default.
- FR-5: The CLI must provide concise default error output and traceback/detail output when `--debug` is enabled.
- FR-6: The CLI must map exceptions to canonical exit codes (`0/2/3/4`) consistently.
- FR-7: The CLI must preserve deterministic JSON output for identical inputs.
- FR-8: The existing `probe` command must remain available.
- FR-9: CLI tests must cover valid command paths, formatting options, and failure-mode exit codes.
- FR-10: Phase 9 must not re-implement business rules already owned by application/domain layers.

## 5. Non-Goals (Out of Scope)

- Golden output snapshot suite and release readiness work (Phase 10).
- Adding additional commands beyond primary calculation and existing `probe`.
- Altering domain formulas, periodization rules, or meal assembly policy from prior phases.
- Persistence, remote services, or cloud integrations.
- Broad UX redesign of terminal output beyond required format/debug support.

## 6. Design Considerations

- Keep command handlers thin and deterministic; delegate business logic to `application`.
- Keep JSON format canonical and automation-friendly.
- Keep format renderers separate from core calculation to avoid cross-coupled logic.

## 7. Technical Considerations

- Reuse existing `shared.exit_codes` mapping helpers.
- Use Typer-native typed options and enum constraints where possible.
- Isolate parsing helpers for `--training-zones` with deterministic error raising.
- Ensure debug traceback behavior is testable and does not pollute normal output path.

## 8. Success Metrics

- CLI command returns deterministic JSON by default for repeated identical inputs.
- Exit codes match canonical mapping across representative error classes.
- `--format` and `--debug` behaviors are stable and covered by CLI tests.
- `probe` command continuity is preserved while production command is introduced.

## 9. Open Questions

- None for Phase 9 scope after clarification decisions (`--format json|text|table`, default concise + debug traceback errors, strict JSON `--training-zones`, keep `probe`).

## 10. Implementation Backlog (Phase 9)

1. Add/extend production `mealplan` command with typed options and request mapping.
2. Implement strict JSON-string parsing helper for `--training-zones`.
3. Wire command handler to `MealPlanCalculationService.calculate(...)`.
4. Add output formatter path for `json|text|table` with default `json`.
5. Implement default error output and `--debug` traceback behavior.
6. Ensure exception-to-exit-code mapping uses canonical `ExitCode` helpers.
7. Keep `probe` command intact and covered.
8. Add CLI integration tests for success formats, parsing errors, propagated failures, and debug behavior.
9. Update architecture/requirements/usage docs for finalized CLI contract.
10. Run `ruff check .`, `mypy --strict src`, and `pytest`.
