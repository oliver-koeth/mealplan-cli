# AGENT.md

## Purpose

This file is for autonomous coding agents working in this repository.  
It defines execution workflow and where to find authoritative project rules without duplicating product specs.

## Canonical References (Do Not Rephrase Here)

- Product requirements: `docs/REQUIREMENTS.md`
- Architecture and layer boundaries: `docs/ARCHITECTURE.md`
- Domain model and invariants: `docs/MODEL.md`
- Build sequencing: `docs/PLAN.md`
- Enhancement lifecycle and artifact flow: `docs/ENHANCEMENTS.md`
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
32. When a phase-level assumption changes (for example required-vs-default inputs), update both `docs/PLAN.md` (phase scope/risks) and `docs/ARCHITECTURE.md` (calculation engine/future evolution) in the same iteration to keep backlog and architecture narratives consistent.
33. When training-fueling boundary ownership changes or is clarified, keep docs synchronized by topic: put architecture-layer ownership in `docs/ARCHITECTURE.md`, functional rule wording in `docs/REQUIREMENTS.md`, and domain contract details in `docs/MODEL.md`.
34. For stable cross-layer domain service interfaces, add a unit test that pins `inspect.signature(...)` so parameter and return-type contract drift is caught early.
35. For canonical meal-keyed mappings that assign one shared scalar value, prefer `dict.fromkeys(CANONICAL_MEAL_ORDER, value)` to satisfy Ruff `C420` and keep deterministic key order.
36. For periodized allocations with selected high meals, compute low-meal residuals from `daily_carbs_g - sum(high allocations)` and divide by `len(CANONICAL_MEAL_ORDER) - len(high_meals)` rather than hardcoding meal counts.
37. For periodization tomorrow-load behavior, treat `training_before_meal in {DINNER, EVENING_SNACK}` as an explicit conflict branch that preserves post-training meal selection and skips the next-day `DINNER` high override.
38. Keep Phase 6 allocation precedence explicit in `calculate_periodized_carb_allocation`: non-periodized bypass first, then post-training high-meal selection, then tomorrow-high override/conflict handling, then reconciliation validation.
39. Keep Phase 6 non-periodized bypass keyed only to carb mode (`LOW`/`NORMAL`): always return canonical equal split `daily_carbs_g / 6.0` with no rounding, independent of training inputs.
40. For tolerance-based domain checks, add both boundary-pass (`delta <= tolerance`) and failure (`delta > tolerance`) tests and assert stable error prefixes rather than full diagnostic strings.
41. For periodization precedence/conflict coverage, build exhaustive matrices from `CANONICAL_MEAL_ORDER x TrainingLoadTomorrow` with stable case IDs and assert both high-meal role selection and reconciliation totals.
42. For domain meal-assembly payloads, build `MealAllocation` rows first and run `validate_meal_allocation_invariants` before serializing dict payloads so canonical order/uniqueness guarantees are enforced at the domain boundary.
43. For Phase 7 meal split regressions, include fractional protein/fat fixtures and assert per-meal values equal exact `total / 6.0` (not boundary-rounded values) to catch early rounding drift.
44. For Phase 7 meal assembly, validate carb allocation keys upfront against exact `CANONICAL_MEAL_ORDER` coverage (no missing/extra keys) and raise `DomainRuleError` with `meal_assembly.carb_allocation` prefix before meal row construction.
45. For Phase 7 response payload serialization, apply `round(..., 2)` only at the meals boundary (`carbs_g`, `protein_g`, `fat_g`) and keep top-level macro fields as canonical unrounded inputs.
46. For Phase 7 meal assembly reconciliation, apply residual correction only to `MealName.EVENING_SNACK`, process macro dimensions in fixed order (`carbs_g`, `protein_g`, `fat_g`), and raise `DomainRuleError` with `meal_assembly.reconciliation` prefix if post-adjustment totals still mismatch targets.
47. For Phase 7 response-shape updates, keep top-level-plus-meals payload construction in a dedicated helper and verify compatibility by parsing assembler output with `MealPlanResponse.model_validate(...)` in domain service tests.
48. For Phase 7 reconciliation failure-path tests, use sub-cent macro targets (more than two decimals) to exercise unreconcilable drift and assert only the stable `meal_assembly.reconciliation` error prefix.
49. For API signature tests on modules using `from __future__ import annotations`, resolve annotations with `typing.get_type_hints(...)` instead of asserting raw `inspect.signature(...).annotation` values, because raw annotations may be strings.
50. In `MealPlanCalculationService`, keep stage composition explicit by returning stage outputs (`tdee_kcal`, `MacroTargets`) and passing them to downstream stage hooks, rather than storing mutable intermediate state on the service instance.
51. For fueling-stage orchestration, normalize request zones first and pass a canonical `1..5` integer-key mapping into `calculate_training_carbs_g` exactly once per `MealPlanCalculationService.calculate(...)` call, then thread `training_carbs_g` into assembly.
52. For omitted optional training input (`training_session=None`), keep orchestration tests that call `MealPlanCalculationService.calculate(...)` without monkeypatching to verify end-to-end zero-training behavior (`training_carbs_g == 0.0`) across representative carb modes.
53. For periodization-stage orchestration, delegate directly to `calculate_periodized_carb_allocation(carb_mode, daily_carbs_g, training_before_meal, training_load_tomorrow)` and pass through the returned meal allocation map without duplicating precedence/override rules in application code.
54. For application assembly-stage orchestration, delegate response dict construction to `calculate_meal_split_and_response_payload(...)` and parse via `MealPlanResponse.model_validate(...)`; avoid hand-building response payloads in `MealPlanCalculationService`.
55. Keep Phase 8 application integration coverage in `tests/unit/test_application_orchestration.py` by invoking `MealPlanCalculationService.calculate(...)` directly across representative success and failure propagation scenarios (`ValidationError` and `DomainRuleError` `meal_assembly.reconciliation`) without CLI coupling.
56. When Phase 8 orchestration API/flow semantics change, update docs in the same iteration across `docs/ARCHITECTURE.md` (service boundary + stage sequence), `docs/REQUIREMENTS.md` (functional flow contract), and `docs/MODEL.md` (application boundary return contract and `training_session=None` interpretation).
57. In CLI modules using Typer, define `typer.Option(...)` objects as module-level constants and reuse them in command signatures to satisfy Ruff `B008` under repository lint settings.
58. For CLI options with a fixed value set (for example output format), annotate Typer parameters with `typing.Literal[...]` (or equivalent enums) so invalid values fail at CLI parse time with exit code `2`.
59. For CLI invalid-JSON coverage (for example `--training-zones`), assert stable stderr prefixes and mapped exit codes rather than full JSON decoder messages, which can vary by runtime version.
60. For CLI boundary-wiring tests, prefer `typer.testing.CliRunner` with `monkeypatch` on `mealplan.cli.main.MealPlanCalculationService` so tests can assert command-to-service delegation and response-driven output without subprocess indirection.
61. For CLI multi-format output (`json`, `text`, `table`), render from `MealPlanResponse.model_dump(mode="json")` and iterate meals via `CANONICAL_MEAL_ORDER` so human-readable formats stay contract-aligned and deterministic.
62. Keep CLI debug behavior centralized in `main()` exception handling: default stderr remains concise (`Error: ...`), and traceback emission is enabled only when command-level debug mode is explicitly set.
63. For CLI exit-code mapping tests that must exercise `main()` exception handling (not just Typer command functions), monkeypatch `sys.argv` with full command args and monkeypatch `mealplan.cli.main.MealPlanCalculationService` to raise representative exceptions, then assert `SystemExit.code`.
64. When CLI contract behavior changes (flags, formats, exit semantics, debug behavior), update docs in the same iteration across `docs/ARCHITECTURE.md` (boundary and error strategy), `docs/REQUIREMENTS.md` (user-facing contract), and `README.md` (concrete command examples).
65. For file-based CLI golden snapshots, store canonical JSON payloads with ordered keys (`exit_code`, `stderr`, `stdout`), normalize newlines, strip ANSI escapes from stderr, and collapse traceback bodies to a placeholder token so snapshots remain deterministic across environments.
66. For application golden snapshots that execute real domain assembly, choose fixture inputs whose computed macro totals are cent-reconcilable at meal level; otherwise strict `meal_assembly.reconciliation` tolerance (`1e-9`) can raise expected `DomainRuleError` and invalidate success fixtures.
67. For golden snapshot comparisons, reuse `tests/golden/helpers.py` hybrid assertions: enforce strict key/list ordering and string fields, and apply only `NUMERIC_TOLERANCE_ABS = 0.01` to approved energy/macro numeric fields (`TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`, and `meals[*].{protein_g,carbs_g,fat_g}`).
68. For packaging verification, run `scripts/checks/verify_package_artifacts.py`: it must execute `uv build`, assert exactly one wheel and one sdist in `dist/`, validate package name/version metadata, and confirm the `mealplan` console entry point in wheel `entry_points.txt`.
69. For installability verification, run `scripts/checks/verify_install_workflow.py` after packaging checks: install `dist/*.whl` into a fresh temp virtualenv, run both `mealplan --help` and `python -m mealplan --help` from outside the repo source tree, and include one `mealplan calculate ... --format json` smoke command.
70. Keep release-readiness steps in `docs/RELEASE_CHECKLIST.md` aligned with executable local/CI gates (`make quality`, `make package-check`, `make install-smoke-check`) so documentation and automation do not drift.
71. Keep CI release-readiness gates split into dependent jobs in `.github/workflows/ci.yml` (`quality` -> `package-build` -> `install-smoke`) and pass built artifacts via `actions/upload-artifact`/`actions/download-artifact` so install-smoke validates the exact wheel produced by packaging.
72. When CI gate commands or job boundaries change, update `README.md` and `CONTRIBUTING.md` in the same iteration so contributor-facing quality/package/install guidance stays synchronized with `.github/workflows/ci.yml` and `docs/RELEASE_CHECKLIST.md`.
73. For net-new incremental features, follow `docs/ENHANCEMENTS.md`: author one `docs/enhancements/enhance-*` brief, generate PRD in `tasks/`, execute from `scripts/ralph/prd.json`, and archive outputs under `scripts/ralph/archive/`.
74. For response-level optional `training` meal support, keep canonical six-meal domain invariants scoped to non-training meals, allow at most one `training` entry, and keep training-row macros carbs-only (`protein_g=0`, `fat_g=0`).
75. For `training` meal ordering, insert at most one `training` row immediately before `training_before_meal`; in response-contract validation, enforce canonical order only after filtering out `training`.
76. In Typer command signatures, avoid union option annotations with multiple non-`None` types (for example `MealName | Literal["training"] | None`), because Typer parameter conversion asserts on such unions; accept `str | None` at CLI and enforce allowed values in contract/semantic validation layers.
77. For meal-level energy display, first recompute each row `kcal` from displayed macros (`4/4/9`), then apply a final display-only `TDEE` reconciliation by adjusting `evening-snack.kcal` so `sum(meals[*].kcal) == TDEE` without mutating meal macros.

## Ralph Runner

- Preflight: `./scripts/ralph/doctor.sh`
- Execute loop: `./scripts/ralph/ralph.sh <max_iterations>`

## Out of Scope for Phase 1

Do not implement nutrition business logic yet (energy/macros/periodization).  
That starts in later phases defined in `docs/PLAN.md`.
