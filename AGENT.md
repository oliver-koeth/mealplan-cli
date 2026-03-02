# AGENT.md

## Purpose

This file is for autonomous coding agents working in this repository.  
It defines execution workflow and where to find authoritative project rules without duplicating product specs.

## Canonical References (Do Not Rephrase Here)

- Product requirements: `docs/REQUIREMENTS.md`
- Architecture and layer boundaries: `docs/ARCHITECTURE.md`
- Domain model and invariants: `docs/MODEL.md`
- Build sequencing: `docs/PLAN.md`
- Human contributor workflow: `CONTRIBUTING.md`

When in doubt, update those source docs instead of expanding this file.

## Current State Snapshot

- Project is in **Phase 1 (Foundation and Scaffolding)** from `docs/PLAN.md`.
- Ralph backlog file: `scripts/ralph/prd.json`
- Branch target in backlog: `ralph/phase-1-foundation-scaffolding`
- As of this snapshot, stories `US-001` through `US-008` are marked complete.

## Agent Execution Rules

1. Work from `scripts/ralph/prd.json` in ascending `priority`.
2. Keep edits scoped to the active story; avoid bundling unrelated refactors.
3. Preserve architectural import direction (see `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`).
4. Run quality gates locally before marking a story complete:
   - `make quality`
5. After completing a story:
   - set that story's `passes` to `true` in `scripts/ralph/prd.json`
   - append a short entry to `scripts/ralph/progress.txt` (what changed, files touched, checks run)
6. If a story reveals reusable repo-level conventions, update this file briefly.
7. Keep CI quality gates in `.github/workflows/ci.yml` aligned with local `make quality` commands.
8. For Phase 2+ contract work, keep domain enum values centralized in `src/mealplan/domain/enums.py` and import from `mealplan.domain.enums`.
9. Use `src/mealplan/domain/model.py` `CANONICAL_MEAL_ORDER` as the single source for meal sequencing; avoid re-declaring meal order lists in other modules.
10. For contract DTOs in `src/mealplan/application/contracts.py`, subclass `BoundaryModel` for every nested model so `extra="forbid"` is enforced at each level, and use strict numeric field types to block string coercion.
11. For constrained `dict` keys in contracts (for example training zones), enforce allowed keys with `Literal` key typing (`dict[Literal[...], StrictInt]`) so invalid keys are rejected during schema parsing.
12. For contract response DTOs, keep meal output ordering enforced at the model boundary (for example with a model validator against `CANONICAL_MEAL_ORDER`) and expose placeholder constructors for pre-calculation phases.
13. Keep contract units metadata in `src/mealplan/application/contracts.py` as `CONTRACT_UNITS_POLICY` and document any legacy naming exceptions (for example `TDEE` as kcal/day) in both code and docs.
14. Parse external payloads through `src/mealplan/application/parsing.py::parse_contract` so pydantic failures are mapped to shared `ValidationError` with stable field-path messages for CLI exit-code handling.
15. Reuse canonical contract test payloads from `tests/unit/conftest.py` fixtures (`meal_plan_request_payload`, `meal_plan_response_payload`) instead of duplicating request/response literals across test modules.
16. For negative contract matrix tests, assert stable pydantic error categories (`error["type"]`) rather than full error-message snapshots to avoid brittle tests.
17. When contract shapes or enum sets change, update `docs/ARCHITECTURE.md` section 10 with canonical module paths, exact request/response field names, canonical meal order usage, Phase 2 schema-vs-Phase 3 semantic boundary, and one valid request/response JSON example.
18. Keep Phase 3 semantic guards in `src/mealplan/application/validation.py::validate_semantic_input`; raise `ValidationError` messages prefixed with the failing field path (for example `age: ...`) to preserve deterministic CLI/user-facing error payloads.
19. Enforce training dependency semantics in application validation using aggregate zone volume (`sum(zones_minutes.values())`): require `training_before_meal` only when total minutes are greater than zero, and report failures as `training_session.training_before_meal: ...`.
20. For any semantic rule that reads `training_session.zones_minutes`, first canonicalize with `normalize_training_zones` (application validation) so subset payloads, numeric-string keys, and deterministic `1..5` coverage are handled consistently.
21. Keep nutrition-output hard invariants in `src/mealplan/domain/validation.py` and raise `DomainRuleError` (not `ValidationError`) for domain impossibilities such as negative macro targets.
22. Validate domain meal-allocation structure through `validate_meal_allocation_invariants` and `CANONICAL_MEAL_ORDER` (count -> canonical coverage -> canonical order) to keep response-shape failures deterministic at the domain boundary.
23. Enforce top-level versus per-meal carb consistency with `validate_carb_reconciliation_invariants` using `CARB_RECONCILIATION_TOLERANCE` (`abs(sum - target) <= 1e-9`) so reconciliation behavior remains deterministic.
24. For Phase 3+ use-case wiring, run `validate_meal_plan_flow` (`application/orchestration.py`) to preserve the canonical order `parse_contract -> validate_semantic_input -> domain invariants` and keep error-type boundaries stable.
25. Keep Phase 3 regression coverage in `tests/unit/test_validation_matrices.py` using parameterized matrices that assert exception class and exit-code category, with only minimal message fragments/prefixes for stability.
26. Keep energy-formula helpers in `src/mealplan/domain/energy.py`, name them with explicit units (for example `*_kcal_per_day_for`), and re-export them via `mealplan.domain.__init__`.
27. For composed energy/macro domain APIs, accept typed `UserProfile` inputs from `src/mealplan/domain/model.py` instead of unstructured payloads so service contracts stay deterministic and cross-layer stable.
28. Keep macro formula helpers in `src/mealplan/domain/macros.py` (protein/carbs mode factors) and re-export public helpers/constants via `mealplan.domain.__init__` for stable imports.
29. When macro formulas derive impossible negative targets (for example residual fat), raise `DomainRuleError` with a stable `macro_targets.<field>` prefix to preserve deterministic domain categorization and CLI exit-code mapping.
30. For composed Phase 4+ domain orchestration entrypoints, use `src/mealplan/domain/services.py` and delegate to formula helpers in `energy.py`/`macros.py`; re-export composed services via `mealplan.domain.__init__` to avoid deep-module imports in higher layers.
31. For floating-point formula regression tests, prefer `pytest.approx` for multiplicative outputs and assert stable error-category prefixes (not full message snapshots) for domain failures.

## Ralph Runner

- Preflight: `./scripts/ralph/doctor.sh`
- Execute loop: `./scripts/ralph/ralph.sh <max_iterations>`

## Out of Scope for Phase 1

Do not implement nutrition business logic yet (energy/macros/periodization).  
That starts in later phases defined in `docs/PLAN.md`.
