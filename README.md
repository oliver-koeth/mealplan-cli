# mealplan-cli

## Directory Layout

The project is organized by architecture layer so features can be added with clear
dependencies:

- `src/mealplan/cli`: command-line entrypoints and user-facing command wiring.
- `src/mealplan/application`: application orchestration and request/response
  boundary contracts.
- `src/mealplan/domain`: pure business rules and domain entities.
- `src/mealplan/infrastructure`: persistence, external integrations, and I/O.
- `src/mealplan/shared`: shared cross-cutting utilities and error contracts.

Tests follow the same intent and are grouped by scope:

- `tests/unit`: isolated fast tests.
- `tests/integration`: integration tests across modules.
- `tests/cli`: command-line behavior tests.
- `tests/golden`: output snapshot/golden file tests.

## Developer Setup

1. Install Python 3.11+ and `uv`.
2. Create and sync the environment:
   `uv sync --dev`
3. Install the package in editable mode:
   `uv pip install -e .`
4. Verify the command entrypoint:
   `uv run mealplan --help`

## Quality Checks

- Run all local quality gates:
  `make quality`
- Verify package artifacts (`sdist` + `wheel`):
  `make package-check`
- Verify isolated wheel install and smoke commands:
  `make install-smoke-check`
- Run checks individually when needed:
  `.venv/bin/uv run ruff check .`
  `.venv/bin/uv run mypy --strict src`
  `.venv/bin/uv run pytest`

## Isolated Wheel Install Workflow

Use this workflow to validate installability outside the source tree:

1. Build artifacts:
   `uv run python scripts/checks/verify_package_artifacts.py`
2. Create a fresh virtual environment:
   `python -m venv /tmp/mealplan-smoke-venv`
3. Install the built wheel:
   `/tmp/mealplan-smoke-venv/bin/pip install dist/*.whl`
4. Run install smoke commands:
   `/tmp/mealplan-smoke-venv/bin/mealplan --help`
   `/tmp/mealplan-smoke-venv/bin/python -m mealplan --help`
   `/tmp/mealplan-smoke-venv/bin/mealplan calculate --age 40 --gender male --height 180 --weight 75 --activity medium --carbs low --training-tomorrow high --format json`

## CLI Usage

- Show command help:
  `uv run mealplan --help`
- Show calculate help:
  `uv run mealplan calculate --help`

`mealplan calculate` accepts these canonical required flags:

- `--age`
- `--gender` (`male|female`)
- `--height` (cm)
- `--weight` (kg)
- `--activity` (`low|medium|high`)
- `--carbs` (`low|normal|periodized`)
- `--training-tomorrow` (`low|medium|high`)

Optional flags:

- `--training-zones` (JSON string only, for example `'{"1": 20, "2": 40}'`)
- `--training-before` (`breakfast|morning-snack|lunch|afternoon-snack|dinner|evening-snack`)
- `--format` (`json|text|table`, default `json`)
- `--debug`

Concrete examples:

```bash
# Default JSON output (stdout)
uv run mealplan calculate \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs low --training-tomorrow high

# Explicit text output with training context
uv run mealplan calculate \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs periodized --training-tomorrow high \
  --training-zones '{"1": 20, "2": 40, "3": 0, "4": 0, "5": 0}' \
  --training-before lunch \
  --format text

# Explicit table output
uv run mealplan calculate \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs normal --training-tomorrow medium \
  --format table
```

## Exit Codes and Debug Behavior

- `0`: success
- `2`: validation/input errors (including invalid flag values and invalid `--training-zones` JSON)
- `3`: domain rule violations
- `4`: runtime/infrastructure failures

Error output behavior:

- Default: concise `Error: ...` message on stderr
- With `--debug`: same message plus traceback details on stderr
- Successful command payloads always stay on stdout

## Golden Snapshot Tolerance Policy

Golden tests use a hybrid policy:

- Strict checks: exact JSON keys, key ordering, list ordering, and all string/enum fields.
- Tolerant checks: numeric fields only for `TDEE`, `training_carbs_g`, `protein_g`, `carbs_g`, `fat_g`, and per-meal macro grams (`meals[*].protein_g`, `meals[*].carbs_g`, `meals[*].fat_g`) with absolute tolerance `0.01`.
- Shared helper: tolerance constants and comparisons are centralized in `tests/golden/helpers.py` and reused by CLI and application golden suites.

## CI Expectations

- GitHub Actions runs on every `push` and `pull_request`.
- CI installs dependencies with `uv sync --dev`.
- CI must pass all quality gates:
  `uv run ruff check .`
  `uv run mypy --strict src`
  `uv run pytest`
- CI also verifies:
  `uv run python scripts/checks/verify_package_artifacts.py`
  `uv run python scripts/checks/verify_install_workflow.py`

## Release Readiness

- Follow `docs/RELEASE_CHECKLIST.md` before publishing a release candidate.
- The checklist covers quality gates, golden snapshot pass criteria, packaging and isolated install-smoke verification, and first usable release versioning/release-note expectations.

## Contributing

Contributor workflow and architecture-boundary expectations are documented in
`CONTRIBUTING.md`.

## Dependency Lock Workflow

- Refresh the lockfile after dependency changes:
  `uv lock`
- Sync to the lockfile contents:
  `uv sync --dev`
