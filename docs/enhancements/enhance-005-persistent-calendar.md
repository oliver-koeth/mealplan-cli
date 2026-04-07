# Enhancement Brief: enhance-005 Persistent Calendar

## Problem statement
Meal plans are currently calculated for immediate output in CLI and web UI flows, but there is no date-based persistence that allows users to save and retrieve plans by day. This blocks basic planning continuity because users cannot revisit a previously calculated day from either interface.

The requested enhancement introduces a persistent date-keyed meal-plan calendar backed by a simple JSON file, available from both the CLI and the web UI.

## Goals
- Add persistent storage for meal plans keyed by date.
- Support date-specific save behavior from CLI `calculate` and web UI calculation flow.
- Add date-specific retrieval behavior from a new CLI `calendar` command and a new web UI `Calendar` view.
- Keep behavior simple and deterministic: writes overwrite existing entries for the same date without confirmation.

## In scope
- Add backend persistence using a simple JSON file for saved meal plans.
- Store meal plans by date, with one plan per date key.
- CLI `calculate`:
  - add `--date` parameter in `YYYYMMDD` format
  - after successful calculation, persist/overwrite meal plan for that date
- CLI `calendar`:
  - add new command/function `calendar`
  - support `--date` in `YYYYMMDD` format
  - support `--format` output options exactly matching `calculate` (`json|text|table`)
  - support `--help`
  - read and return meal plan for the date from persistent storage
  - log an error when no plan exists for the requested date and exit with code `3` (`ExitCode.DOMAIN`)
- Web UI settings defaults:
  - include `activity`, `training_before`, and `training_tomorrow`
  - use same value ranges/options as `calculate`
  - persist these defaults in browser local storage
- Web UI `Calculate` view:
  - add a date picker on the same line as `DAY INPUTS/RESULTS`
  - add `"<"` and `">"` buttons to move one day backward/forward
  - initialize date picker with current date
  - date picker captures date only (no time)
  - convert selected date to canonical `YYYYMMDD` before backend submission
  - on successful calculate + `Save`, write the meal plan for selected date to backend storage
  - overwrite existing meal plan for same date without notice
- Web UI `Calendar` view:
  - add new top-level view next to `Settings` and `Calculate` named `Calendar`
  - use layout similar to `Calculate`
  - include date picker and `"<"` / `">"` day navigation buttons
  - initialize date picker with current date
  - date picker captures date only (no time)
  - convert selected date to canonical `YYYYMMDD` before backend lookup
  - fetch meal plan for selected date from backend
  - display plan in the same visual style as calculate results modal
  - do not allow kcal adjustment controls (`+100`/`-100`) in calendar display
  - if no plan exists, show: `No meal plan exists, you first need to calculate one`
  - make `calculate` in that message a link to the `Calculate` view

## Out of scope
- Multi-user support, authentication, or cloud sync.
- Conflict resolution/version history for multiple saves on the same date.
- Notifications or confirmation dialogs before overwrite.
- Any change to nutrition calculation logic itself.
- Advanced database storage; persistence remains single JSON-file based.

## Constraints and assumptions
- Canonical date format is `YYYYMMDD` everywhere:
  - CLI input
  - backend JSON storage keys
  - API request/response date fields used for persistence lookup/write
- Web UI date pickers are date-only controls and may render locale-specific display formats in the browser; this is acceptable as long as submitted/looked-up values are converted to canonical `YYYYMMDD`.
- Date parsing/validation errors should be handled as user-facing validation errors in both CLI and API paths.
- Calendar persistence backend is file-based JSON and must auto-create an empty store file when absent.
- Storage read/write behavior should be deterministic and safe for normal single-process local usage.
- Existing-day writes always replace the stored meal plan entirely for that date.
- The `Calendar` view is read-only for stored plans.
- Existing `calculate` behavior for rendering immediate results remains unchanged except for date handling and save persistence.

## Definition of done
- Backend persistence layer exists and stores meal plans in a JSON file keyed by date.
- CLI `calculate` supports `--date YYYYMMDD` and overwrites persisted meal plan for that date after successful calculation.
- CLI `calendar` command exists with `--date YYYYMMDD`, `--format`, and `--help`.
- CLI `calendar` returns stored meal plan in selected format and logs an error if the date has no stored plan, exiting with code `3` (`ExitCode.DOMAIN`).
- Web UI settings defaults include `activity`, `training_before`, and `training_tomorrow`, with values persisted in local storage.
- Web UI `Calculate` includes date picker plus day-step buttons and initializes to current date.
- Web UI save from calculate results persists meal plan to backend for selected date with overwrite semantics.
- Web UI `Calendar` view exists at top-level navigation and initializes to current date.
- Web UI `Calendar` fetches and displays stored meal plan for selected date in calculate-results style, without `+100/-100` adjustments.
- Missing-plan state in `Calendar` shows the required message with `calculate` linked to the calculate view.
- Tests cover:
  - CLI date validation for both commands
  - overwrite behavior for same-date saves
  - not-found behavior for calendar lookup
  - API/backend persistence and retrieval path
  - UI date initialization and day-step navigation
  - UI save-to-backend and calendar retrieval rendering
  - UI read-only calendar rendering without kcal adjustment controls

## Open questions
- None for this enhancement scope after clarification.
