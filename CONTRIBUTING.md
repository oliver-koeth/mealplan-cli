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
