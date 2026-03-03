# Contributing to `mealplan-cli`

## Local Setup

1. Install Python `3.11+`.
2. Install `uv`.
3. Sync dependencies (including dev tools):
   `.venv/bin/uv sync --dev`
4. Verify the CLI entrypoint:
   `.venv/bin/uv run mealplan --help`

## Pre-Commit Quality Commands

Run these before opening a pull request:

1. `.venv/bin/uv run ruff check .`
2. `.venv/bin/uv run mypy --strict src`
3. `.venv/bin/uv run pytest`

You can also run all gates with:

- `make quality`

Release-readiness checks are also expected for packaging-related changes:

- `make package-check`
- `make install-smoke-check`

## Golden Snapshot Workflow

When changing CLI output or application response shape, update and verify golden fixtures:

1. Run golden suites:
   `uv run pytest tests/golden`
2. Keep fixture content deterministic:
   - CLI fixtures use canonical envelope keys: `exit_code`, `stderr`, `stdout`.
   - Normalize stderr before assertions (no ANSI control sequences; traceback bodies collapsed).
   - Keep canonical meal ordering and stable JSON key ordering in fixture files.
3. Re-run full quality gates:
   `make quality`

## Architecture Boundary Expectations

Keep imports and responsibilities aligned with the architecture:

- `src/mealplan/cli`: command wiring, argument parsing, user-facing output only.
- `src/mealplan/application`: use-case orchestration and boundary request/response
  contracts.
- `src/mealplan/domain`: pure business rules and domain entities only.
- `src/mealplan/infrastructure`: I/O, persistence, config loading, and external
  integrations.
- `src/mealplan/shared`: cross-cutting concerns shared by multiple layers.

Import direction must remain inward:

- CLI can import `application` and `shared`.
- Application can import `domain` and `shared`.
- Domain must not import CLI or infrastructure modules.
