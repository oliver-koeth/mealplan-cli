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
