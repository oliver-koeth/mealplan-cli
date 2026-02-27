# PRD: Phase 2 Canonical Contracts and Validation

## 1. Introduction/Overview

Phase 2 defines the canonical request/response contracts and core enumerations for `mealplan`, with deterministic schema-level validation at the application boundary.

This phase locks model shapes, allowed values, and canonical meal ordering so later calculation phases can rely on stable interfaces. It explicitly excludes business-rule and cross-field domain invariants planned for later phases.

## 2. Goals

- Implement canonical enums and value definitions from `docs/MODEL.md`.
- Define full request and response DTOs at the application boundary using pydantic.
- Centralize one canonical meal sequence as a shared source of truth.
- Enforce schema-level validation (types, required fields, enum membership) only.
- Provide contract tests that prove field requirements, allowed values, and serialization stability.

## 3. User Stories

### US-001: Implement canonical enums
**Description:** As a developer, I want canonical enums for required domain dimensions so all layers use the same allowed values.

**Acceptance Criteria:**
- [ ] Add enums for `Gender`, `ActivityLevel`, `CarbMode`, `TrainingLoadTomorrow`, and `MealName`
- [ ] Enum members and serialized values align with `docs/MODEL.md`
- [ ] Enums are imported from one canonical module path
- [ ] Unit tests verify accepted enum values and reject unknown values
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-002: Define canonical meal order constant
**Description:** As a developer, I want one shared meal sequence so all allocation and output code uses deterministic ordering.

**Acceptance Criteria:**
- [ ] Add a single exported constant for canonical meal order in the domain model module
- [ ] Sequence includes six unique `MealName` entries
- [ ] Order is deterministic and documented in module docstring or comments
- [ ] Tests verify uniqueness, count, and exact order
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-003: Create request DTO with schema validation
**Description:** As an application service, I want a typed request contract so incoming CLI payloads are parsed consistently.

**Acceptance Criteria:**
- [ ] Implement pydantic request DTO containing all required Phase 2 fields from requirements/model docs
- [ ] Required fields fail fast when absent
- [ ] Enum fields accept only canonical enum values
- [ ] Numeric fields enforce type parsing at schema level
- [ ] No business-rule checks are added (for example range/invariant rules beyond schema typing)
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-004: Add training zones contract shape
**Description:** As a developer, I want a typed training-zones structure in the request DTO so future fueling logic has a stable input shape.

**Acceptance Criteria:**
- [ ] Request DTO includes a typed structure for zone minutes keyed by zone identifier
- [ ] Missing training-zones field behavior is explicitly defined (required vs optional with default)
- [ ] Schema-level parsing errors return typed validation errors
- [ ] Contract tests cover valid parsing and invalid type payloads
- [ ] No cross-field dependency checks are added in this phase
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-005: Define full response DTO shape
**Description:** As a consumer of application output, I want a complete response contract now so later phases can fill values without breaking interface stability.

**Acceptance Criteria:**
- [ ] Implement full top-level response DTO and `meals[]` DTO structure
- [ ] Meal entries include meal identity and macro fields required by requirements
- [ ] Response supports deterministic JSON serialization order by model definition
- [ ] Placeholder/stub values can be instantiated for non-implemented calculations
- [ ] Contract tests verify serialization keys and nested structure
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-006: Standardize units policy in contracts
**Description:** As a developer, I want explicit units policy in DTOs so all consumers interpret numeric values consistently.

**Acceptance Criteria:**
- [ ] Document units for each numeric contract field (for example kcal, grams)
- [ ] Units policy lives with contract definitions (docstrings/comments or adjacent docs)
- [ ] Tests assert expected field names that encode or map to units policy
- [ ] No rounding policy implementation is introduced in this phase
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-007: Wire typed validation errors at contract boundary
**Description:** As a CLI/application boundary, I want parsing failures to map to existing typed validation errors.

**Acceptance Criteria:**
- [ ] Contract parse failures are wrapped/mapped to `ValidationError`
- [ ] Mapping behavior is deterministic and unit-tested
- [ ] Error payload/message includes enough detail to identify invalid field
- [ ] Exit-code pathway remains compatible with Phase 1 shared exit codes
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-008: Add positive contract fixtures
**Description:** As a test author, I want canonical valid request/response fixtures so future phases can reuse stable contract examples.

**Acceptance Criteria:**
- [ ] Add reusable valid request fixture covering all required request fields
- [ ] Add reusable valid response fixture covering all response and meal fields
- [ ] Fixtures are deterministic and free of time/random dependencies
- [ ] Tests consume fixtures in at least two contract test modules
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-009: Add negative contract matrix tests
**Description:** As a maintainer, I want matrix-style invalid-input tests so schema regressions are caught immediately.

**Acceptance Criteria:**
- [ ] Add parameterized tests for missing required fields
- [ ] Add parameterized tests for invalid enum values
- [ ] Add parameterized tests for wrong primitive types (string instead of number, etc.)
- [ ] Add parameterized tests for malformed nested structures (for example invalid `meals[]` item shape)
- [ ] Tests assert stable failure type/category, not brittle full-message snapshots
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

### US-010: Document canonical contracts for downstream phases
**Description:** As a contributor, I want concise contract documentation so calculation and CLI phases can integrate without ambiguity.

**Acceptance Criteria:**
- [ ] Update docs to reference canonical enum module and DTO module paths
- [ ] Document canonical meal order and where it must be used
- [ ] Document explicit boundary: schema validation in Phase 2, business-rule/invariant validation deferred
- [ ] Provide one example valid request and response JSON snippet in docs
- [ ] `ruff check .` passes
- [ ] `mypy --strict src` passes
- [ ] `pytest` passes

## 4. Functional Requirements

- FR-1: The system must provide canonical enums for `Gender`, `ActivityLevel`, `CarbMode`, `TrainingLoadTomorrow`, and `MealName`.
- FR-2: The system must define one shared canonical meal-order sequence in a single domain model module.
- FR-3: The system must expose pydantic request DTOs containing all Phase 2 required fields.
- FR-4: Request DTO parsing must enforce required fields, type shape, and enum membership.
- FR-5: The system must expose full response DTOs, including top-level totals and ordered `meals[]` entries.
- FR-6: Contract modules must document units policy for numeric fields.
- FR-7: Contract-boundary parse failures must map to typed `ValidationError` behavior.
- FR-8: Contract tests must cover positive examples and negative schema matrix cases.
- FR-9: Contract serialization must be deterministic for identical input payloads.
- FR-10: All contract code must pass `ruff`, `mypy --strict`, and `pytest` gates.

## 5. Non-Goals (Out of Scope)

- Domain invariant enforcement (for example fat non-negative, carb reconciliation, six-unique-meals invariant checks).
- Cross-field business validation (for example `training-before` dependency rules when training minutes exist).
- Energy/macro calculations, training fueling logic, or periodization allocation.
- Rounding policy and residual-adjustment logic.
- CLI flag redesign or output formatting enhancements beyond existing pathways.

## 6. Design Considerations

- Keep canonical enum and meal-order definitions in a domain model-focused module for reuse.
- Keep pydantic contracts at the application boundary, not inside CLI handlers.
- Use explicit field names that align with requirements terminology to reduce mapping ambiguity.

## 7. Technical Considerations

- Contract technology is pydantic-only for boundary models in this phase.
- Validation scope is intentionally limited to schema-level concerns.
- Tests should prefer parameterized matrices for invalid payloads to reduce duplication.
- Preserve architectural boundaries from `docs/ARCHITECTURE.md` (CLI -> application -> domain).

## 8. Success Metrics

- All canonical enums and DTOs are implemented and referenced from stable module paths.
- Contract tests reliably fail on malformed payloads and pass on valid fixtures.
- Repeated serialization of identical DTO instances produces deterministic JSON output.
- Downstream phases can import contracts without changing field names or enum values.

## 9. Open Questions

- Should request DTO numeric types accept coercion from numeric strings, or require strict numeric input only?
- Should training-zone keys be represented as enum keys, integer-like keys, or normalized string keys in the public contract?
- Should response DTO include optional diagnostic/meta fields now, or defer all metadata until debug-mode requirements in CLI phase?
