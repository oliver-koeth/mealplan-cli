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
3. Verify the command entrypoint:
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
4. Run install smoke commands from a directory outside this repository:
   `cd /tmp`
   `/tmp/mealplan-smoke-venv/bin/mealplan --help`
   `/tmp/mealplan-smoke-venv/bin/python -m mealplan --help`
   `/tmp/mealplan-smoke-venv/bin/mealplan calculate --date 20260406 --age 40 --gender male --height 180 --weight 75 --activity medium --carbs low --training-tomorrow high --format json`
   `/tmp/mealplan-smoke-venv/bin/mealplan calendar --date 20260406 --format json`
   `/tmp/mealplan-smoke-venv/bin/mealplan --ui` (then verify `/calculate`, `/calendar`, `/api/v1/health`, and `/api/v1/calendar/20260406`)

## Packaged Execution Paths

After installing from `dist/*.whl`, both execution paths are supported:

- Console script entrypoint:
  `mealplan --help`
- Python module execution path:
  `python -m mealplan --help`

Representative packaged usage examples:

```bash
# JSON output via console script
mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs low --training-tomorrow high --format json

# Text output via module invocation
python -m mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs periodized --training-tomorrow high \
  --training-zones '{"1": 20, "2": 40, "3": 0, "4": 0, "5": 0}' \
  --training-before lunch --format text

# Table output via console script
mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs normal --training-tomorrow medium --format table

# Retrieve a previously saved plan for a date
mealplan calendar --date 20260406 --format json

# Create a food log entry
mealplan log --date 20260408 --meal lunch --name Oats --kcal 380 --carbs 55 --fat 8 --protein 14 --fiber 9

# Search persisted food log entries
mealplan log search --date 20260408 --name yogurt --meal lunch
```

## CLI Usage

- Show command help:
  `uv run mealplan --help`
- Show calculate help:
  `uv run mealplan calculate --help`
- Show calendar help:
  `uv run mealplan calendar --help`
- Show log help:
  `uv run mealplan log --help`

`mealplan calculate` accepts these canonical required flags:

- `--date` (`YYYYMMDD`)
- `--age`
- `--gender` (`male|female`)
- `--height` (cm)
- `--weight` (kg)
- `--activity` (`low|medium|high`)
- `--carbs` (`low|normal|periodized`)
- `--training-tomorrow` (`low|medium|high`)

Optional flags:

- `--vo2max` (integer `10..100`, optional explicit VO2max in `ml/kg/min`)
- `--training-zones` (JSON string only, for example `'{"1": 20, "2": 40}'`)
- `--training-before` (`breakfast|morning-snack|lunch|afternoon-snack|dinner|evening-snack`)
- `--format` (`json|text|table`, default `json`)
- `--debug`

`mealplan calendar` accepts:

- `--date` (`YYYYMMDD`, required)
- `--format` (`json|text|table`, default `json`)

`mealplan log` accepts create/update inputs:

- required (flag mode): `--date`, `--meal`, `--name`, `--kcal`, `--carbs`, `--fat`, `--protein`, `--fiber`
- optional: `--uuid` (update mode), `--quantity` (defaults to `1.0`), `--json` (exclusive one-shot payload mode)

`mealplan log search` accepts optional filters:

- `--date` (`YYYYMMDD`)
- `--name` (case-insensitive substring match)
- `--meal`

Concrete examples:

```bash
# Default JSON output (stdout)
uv run mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs low --training-tomorrow high

# Explicit text output with training context
uv run mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs periodized --training-tomorrow high \
  --vo2max 58 \
  --training-zones '{"1": 20, "2": 40, "3": 0, "4": 0, "5": 0}' \
  --training-before lunch \
  --format text

# Explicit table output
uv run mealplan calculate \
  --date 20260406 \
  --age 40 --gender male --height 180 --weight 75 \
  --activity medium --carbs normal --training-tomorrow medium \
  --format table

# Retrieve date-keyed persisted plan
uv run mealplan calendar --date 20260406 --format text

# Create via one-shot JSON payload (uuid omitted => create)
uv run mealplan log --json '{"date":"20260408","meal":"lunch","name":"Oats","kcal":380,"carbs":55,"fat":8,"protein":14,"fiber":9}'

# Update via one-shot JSON payload (uuid included => update)
uv run mealplan log --json '{"uuid":"<entry-uuid>","date":"20260408","meal":"lunch","name":"Oats + milk","kcal":400,"carbs":58,"fat":9,"protein":15,"fiber":10}'

# Search with optional-AND filters
uv run mealplan log search --date 20260408 --name yog --meal breakfast
```

Date-keyed storage defaults to `~/.mealplan/calendar.json`. Override with
`MEALPLAN_CALENDAR_STORE_PATH` when needed for isolated runs or tests.

Food-log storage defaults to `~/.mealplan/food-log.json`. Override with
`MEALPLAN_FOOD_LOG_STORE_PATH` when needed for isolated runs or tests.

## Local UI Mode

- Start local UI mode:
  `uv run mealplan --ui`
- Startup behavior:
  - Binds to `127.0.0.1` and prefers port `8765` (falls back sequentially through `8775`)
  - Prints:
    - `UI available at http://127.0.0.1:<port>/calculate`
    - `Health endpoint: http://127.0.0.1:<port>/api/v1/health`
  - Does not auto-launch a browser
- Local endpoints:
  - UI routes: `/settings`, `/calculate`, `/calendar`, `/log`
  - API routes: `GET /api/v1/health`, `POST /api/v1/calculate`, `PUT /api/v1/calendar/{date}`, `GET /api/v1/calendar/{date}`, `POST /api/v1/log`, `PUT /api/v1/log/{uuid}`, `GET /api/v1/log/search`

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
- Tolerant checks: numeric fields only for `TDEE`, `training_kcal`, `protein_g`, `carbs_g`, `fat_g`, `total_kcal`, and `meals[*].{protein_g,carbs_g,fat_g,kcal}` with absolute tolerance `0.01`.
- Shared helper: tolerance constants and comparisons are centralized in `tests/golden/helpers.py` and reused by CLI and application golden suites.
- Deterministic fixture rules:
  - CLI snapshots must use canonical keys in this order: `exit_code`, `stderr`, `stdout`.
  - Normalize stderr before fixture comparison (strip ANSI escapes and collapse traceback bodies).
  - Serialize fixture files with sorted keys and a trailing newline to keep local/CI output stable.

## CI Expectations

GitHub Actions runs on every `push` and `pull_request` with three dependent jobs:

- `quality`
  - `uv sync --dev`
  - `uv run ruff check .`
  - `uv run mypy --strict src`
  - `uv run pytest tests/golden`
  - `uv run pytest --ignore=tests/golden`
- `package-build` (needs `quality`)
  - `uv run python scripts/checks/verify_package_artifacts.py`
  - uploads `dist/*` as workflow artifacts
- `install-smoke` (needs `package-build`)
  - downloads `dist/*` artifacts
  - `uv run python scripts/checks/verify_install_workflow.py` (console/module commands + packaged `--ui` shell/API smoke)

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
