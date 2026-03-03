# PRD: Phase 10 Golden Tests, Packaging, and Release Readiness

## 1. Introduction/Overview

Phase 10 closes delivery by adding a deterministic regression safety net and production-facing packaging/release readiness controls.

This phase implements:
- Golden snapshot coverage for both CLI outputs and application responses.
- Packaging verification for both build artifacts and installable workflows.
- Release readiness controls via both documented manual checklist and CI automation.

The phase is focused on stability and ship confidence, not new business logic.

## 2. Goals

- Add deterministic golden tests for critical CLI and application scenarios.
- Enforce a hybrid snapshot policy:
  - strict for structure, ordering, and canonical field presence
  - explicit tolerance strategy for selected numeric fields where needed
- Ensure package build outputs (`sdist`, `wheel`) are consistently produced.
- Ensure local installability and runnable command workflow are verified.
- Add release checklist documentation and CI automation for packaging/release smoke checks.
- Keep behavior aligned with existing contracts, validation, and CLI semantics from Phases 1-9.

## 3. User Stories

### US-001: Add CLI golden snapshot regression suite
**Description:** As a maintainer, I want golden snapshots for critical CLI outputs so user-facing behavior regressions are caught immediately.

**Acceptance Criteria:**
- [ ] Add snapshot tests for representative `mealplan calculate` scenarios across `--format json|text|table`.
- [ ] Include representative CLI failure-mode snapshots (validation/typed option errors, concise error path, debug traceback path).
- [ ] Snapshots assert canonical structure/order and stable phrasing where expected.
- [ ] Snapshot tests are deterministic across repeated local runs.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-002: Add application golden snapshot regression suite
**Description:** As a maintainer, I want golden snapshots of application-level responses so orchestration/domain regressions are detected independently from CLI formatting.

**Acceptance Criteria:**
- [ ] Add snapshot tests for representative `MealPlanCalculationService` success scenarios.
- [ ] Cover both periodized and non-periodized representative paths, including omitted training session behavior.
- [ ] Snapshots validate canonical meal ordering and response shape consistency.
- [ ] Snapshot suite avoids CLI rendering dependencies.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-003: Implement hybrid snapshot tolerance policy
**Description:** As a test author, I want strict structural snapshots and explicit numeric tolerance handling so tests are stable without masking real regressions.

**Acceptance Criteria:**
- [ ] Define and document which fields are strict vs tolerance-aware.
- [ ] Enforce strict checks for payload keys, canonical ordering, and enum/string values.
- [ ] Apply explicit tolerance assertions only to approved numeric fields.
- [ ] Tolerance values are centralized and documented.
- [ ] Tests fail with actionable diff messages when strict or tolerance checks regress.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-004: Verify package artifact builds
**Description:** As a release owner, I want reproducible package build artifacts so the project can be distributed safely.

**Acceptance Criteria:**
- [ ] Add build verification for both source distribution (`sdist`) and wheel (`.whl`).
- [ ] Build outputs are generated through a documented command path.
- [ ] Generated artifacts contain expected package metadata and entry points.
- [ ] Build checks are automated in CI.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-005: Verify pip-installable and runnable workflow
**Description:** As a user, I want a clean install-and-run path so I can use the tool outside the source tree.

**Acceptance Criteria:**
- [ ] Document and test `pip install .` workflow in an isolated environment.
- [ ] Verify installed command invocation (`mealplan` and/or `python -m mealplan`) works as expected.
- [ ] Include at least one smoke command validation post-install.
- [ ] Installability checks are automated in CI.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-006: Add release checklist documentation
**Description:** As a maintainer, I want a concrete release checklist so each release candidate is validated consistently.

**Acceptance Criteria:**
- [ ] Add a release-readiness checklist document with pre-release gates.
- [ ] Checklist includes quality gates, snapshot pass criteria, packaging checks, and smoke install checks.
- [ ] Checklist includes versioning/release notes expectations for first usable release.
- [ ] Checklist references exact commands and expected outcomes.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-007: Add CI automation for release-readiness gates
**Description:** As a maintainer, I want CI automation for packaging and release smoke checks so regressions are blocked before merge.

**Acceptance Criteria:**
- [ ] CI runs golden snapshot suites (CLI and application) as part of standard test workflow.
- [ ] CI adds packaging build job for `sdist` and wheel.
- [ ] CI adds install-and-smoke job in isolated environment.
- [ ] CI surfaces clear failure diagnostics for snapshot drift and packaging/install failures.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

### US-008: Update docs and examples for release-ready usage
**Description:** As a user, I want up-to-date usage and packaging docs so installation and command execution are unambiguous.

**Acceptance Criteria:**
- [ ] Update README/docs with installation and execution paths for packaged usage.
- [ ] Document deterministic output expectations and golden-test intent at a contributor level.
- [ ] Add/refresh examples for common CLI usage in release context.
- [ ] Ensure docs align with implemented CI/release checklist flow.
- [ ] `ruff check .` passes.
- [ ] `mypy --strict src` passes.
- [ ] `pytest` passes.

## 4. Functional Requirements

- FR-1: The system must provide golden regression tests for both CLI outputs and application service responses.
- FR-2: Golden tests must include representative success and failure scenarios for CLI behavior.
- FR-3: Golden tests must enforce canonical ordering and structural stability strictly.
- FR-4: Numeric comparisons in snapshot coverage must follow an explicit, documented tolerance policy for approved fields only.
- FR-5: The project must successfully build `sdist` and wheel artifacts through documented commands.
- FR-6: The project must support isolated installation via `pip install .` and successful post-install smoke invocation.
- FR-7: CI must automate snapshot checks, artifact builds, and installability smoke checks.
- FR-8: Release-readiness documentation must define manual gate criteria and exact verification commands.
- FR-9: Phase 10 must preserve existing functional behavior from Phases 1-9 (no formula/rule changes).
- FR-10: Phase 10 outputs must support first usable release confidence.

## 5. Non-Goals (Out of Scope)

- Adding new meal-planning business rules, formulas, or policy changes.
- Introducing new user-facing commands beyond established Phase 9 surface.
- Expanding into publishing to package registries (e.g., PyPI publish pipeline) unless explicitly requested later.
- Reworking architecture boundaries established in earlier phases.
- Adding non-essential feature work unrelated to regression safety or release readiness.

## 6. Design Considerations

- Keep snapshot fixtures readable and reviewable; prefer canonicalized representations.
- Separate snapshot data from assertion helpers to reduce churn when only policy changes.
- Ensure failure diffs are concise and actionable for contributors.
- Keep CI jobs modular so failures identify the exact gate that regressed.

## 7. Technical Considerations

- Reuse current tooling stack (`pytest`, `ruff`, `mypy`, existing CI workflow).
- Prefer deterministic fixture generation with no time/random/network dependencies.
- Ensure snapshots are stable across environments (terminal formatting differences, locale-neutral behavior).
- Use isolated install verification to prove package metadata/entrypoint correctness outside editable source execution.
- Keep tolerance constants centralized and typed to avoid hidden drift.

## 8. Success Metrics

- Golden suites (CLI + application) pass deterministically across repeated runs and CI.
- Snapshot policy catches structural regressions without flaky numeric noise.
- CI consistently produces `sdist` and wheel artifacts.
- Install-and-smoke checks pass in CI and documented local flow.
- Release checklist is complete and executable by maintainers without ad hoc steps.

## 9. Open Questions

- Should Phase 10 include optional TestPyPI dry-run publication checks, or keep publication entirely post-Phase 10?
- Should snapshot update workflow require explicit contributor command/documented approval gate?

## 10. Implementation Backlog (Phase 10)

1. Define critical scenario matrix for CLI and application golden coverage.
2. Add CLI golden snapshot tests for success formats and representative failure/error rendering paths.
3. Add application golden snapshot tests for representative orchestration outcomes.
4. Implement shared snapshot assertion helpers with hybrid strict/tolerance policy.
5. Document tolerance policy and approved numeric fields.
6. Add packaging build verification for `sdist` and wheel.
7. Add isolated install-and-smoke verification path for packaged invocation.
8. Extend CI workflow with snapshot, packaging, and installability jobs.
9. Add release checklist documentation with exact gate commands.
10. Update README/docs for packaged usage and release-ready contributor workflow.
11. Run `ruff check .`, `mypy --strict src`, and `pytest`.
