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
- Run checks individually when needed:
  `.venv/bin/uv run ruff check .`
  `.venv/bin/uv run mypy --strict src`
  `.venv/bin/uv run pytest`

## Dependency Lock Workflow

- Refresh the lockfile after dependency changes:
  `uv lock`
- Sync to the lockfile contents:
  `uv sync --dev`
