# PRD: Enhance-005 Persistent Calendar

## 1. Introduction/Overview

This enhancement adds persistent, date-keyed meal-plan storage across both CLI and web UI flows. Today, calculated plans are transient and cannot be reliably revisited by day. The new behavior introduces a simple JSON-file persistence backend so users can save and retrieve one meal plan per date.

The enhancement extends CLI with date-aware persistence and retrieval, and extends the web UI with date-aware calculation saving plus a new read-only Calendar view. Canonical date format is fixed to `YYYYMMDD` everywhere, including CLI input, API persistence contracts, and backend storage keys. Existing entries for the same date are overwritten without confirmation.

## 2. Goals

- Persist meal plans by date using a simple JSON backend.
- Add CLI date-aware save behavior to `calculate`.
- Add CLI `calendar` retrieval command with the same output formats as `calculate`.
- Add date-aware save behavior to web `Calculate` results `Save` action.
- Add a web `Calendar` view to retrieve and display stored plans by date.
- Keep persistence semantics deterministic: last write for a date wins.
- Keep UI date controls date-only and normalize to `YYYYMMDD` before backend calls.

## 3. User Stories

### US-001: Add JSON file persistence store for date-keyed meal plans
**Description:** As a maintainer, I want a simple file-backed storage adapter so that meal plans can be persisted and retrieved by date without adding a database.

**Acceptance Criteria:**
- [ ] Add a persistence component that stores one meal-plan payload per date key.
- [ ] Storage format is JSON file based and human-inspectable.
- [ ] Canonical persisted key format is `YYYYMMDD`.
- [ ] Store file is created automatically when missing.
- [ ] Saving for an existing date overwrites prior stored payload for that date.
- [ ] Retrieval for a missing date returns a deterministic not-found error pathway.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-002: Extend CLI calculate with required --date persistence behavior
**Description:** As a CLI user, I want `calculate` to accept a date and persist results for that date so that I can build a day-by-day historical calendar from terminal workflows.

**Acceptance Criteria:**
- [ ] `mealplan calculate` accepts `--date` in `YYYYMMDD` format.
- [ ] Invalid date format is rejected as validation error.
- [ ] On successful calculation, output behavior remains unchanged for the selected `--format`.
- [ ] On successful calculation, the resulting meal plan is saved to persistent storage under the provided date key.
- [ ] If a meal plan already exists for that date, it is overwritten without confirmation.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Add CLI calendar command for date-based retrieval
**Description:** As a CLI user, I want a `calendar` command to retrieve persisted meal plans by date so that I can inspect prior plans without recalculating.

**Acceptance Criteria:**
- [ ] Add `mealplan calendar` command.
- [ ] `calendar` accepts required `--date` in `YYYYMMDD` format.
- [ ] `calendar` accepts `--format` with exactly the same supported values as `calculate`: `json|text|table`.
- [ ] `calendar --help` is available and documents date and format behavior.
- [ ] When a plan exists for the date, output renders in requested format.
- [ ] When no plan exists for the date, an error is logged and process exits with code `3` (`ExitCode.DOMAIN`).
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-004: Add web API endpoints for calendar persistence and retrieval
**Description:** As the web UI, I want backend endpoints for writing and reading date-keyed meal plans so that Save and Calendar views work without CLI coupling.

**Acceptance Criteria:**
- [ ] Add `PUT /api/v1/calendar/{date}` to persist a meal plan for a specific date.
- [ ] Add `GET /api/v1/calendar/{date}` to fetch a meal plan for a specific date.
- [ ] Date parameters for both endpoints are validated and normalized to canonical `YYYYMMDD`.
- [ ] Writing to an existing date overwrites without warning.
- [ ] Missing-date retrieval returns structured not-found error suitable for UI handling.
- [ ] Error response shape remains canonical for UI-facing API errors.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-005: Persist additional planning defaults in web settings local storage
**Description:** As a repeat web user, I want planning defaults for activity and training context saved in settings so that day planning starts with my usual selections.

**Acceptance Criteria:**
- [ ] Settings defaults include `activity`, `training_before`, and `training_tomorrow`.
- [ ] Allowed values match calculate form enum/range options exactly.
- [ ] Settings defaults persist in browser local storage.
- [ ] Calculate view initialization can consume these defaults when day values are unset.
- [ ] Existing settings persistence behavior remains functional.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-006: Add date picker controls to Calculate and wire Save to backend persistence
**Description:** As a web user, I want date-aware calculation and saving so that each calculated plan is stored for the intended day.

**Acceptance Criteria:**
- [ ] `Calculate` view adds date controls on the same row as `DAY INPUTS/RESULTS`.
- [ ] Date controls include date picker plus `"<"` and `">"` buttons for day decrement/increment.
- [ ] Date control initializes to current local date.
- [ ] Date control is date-only (no time input).
- [ ] Browser-locale-specific date rendering is acceptable.
- [ ] Before backend calls, selected date is converted to canonical `YYYYMMDD`.
- [ ] After successful calculate, pressing `Save` writes the displayed meal plan for selected date to backend persistence.
- [ ] Save overwrites existing plan for that date without confirmation.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-007: Add top-level Calendar web view with date navigation and read-only plan display
**Description:** As a web user, I want a dedicated Calendar page to look up persisted plans by date so that I can review prior or future day plans.

**Acceptance Criteria:**
- [ ] Add top-level `Calendar` view alongside `Settings` and `Calculate` navigation.
- [ ] Calendar view layout is consistent with Calculate-page design language.
- [ ] Calendar view includes date picker plus `"<"` and `">"` buttons.
- [ ] Calendar date initializes to current local date.
- [ ] Calendar date is converted to canonical `YYYYMMDD` before backend lookup.
- [ ] When a plan exists, display uses the same information structure as calculate results.
- [ ] Calendar display is read-only and does not show `+100/-100` adjustment controls.
- [ ] When no plan exists, show exact message: `No meal plan exists, you first need to calculate one`.
- [ ] In the missing-plan message, `calculate` links to the Calculate view.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-008: Keep contracts, docs, and regression tests aligned for persistent calendar behavior
**Description:** As a maintainer, I want tests and docs updated for date-based persistence so that the workflow remains stable and understandable.

**Acceptance Criteria:**
- [ ] Add tests for CLI `calculate --date` validation and overwrite behavior.
- [ ] Add tests for CLI `calendar` retrieval, format rendering, and missing-date exit code `3` behavior.
- [ ] Add API tests for `PUT /api/v1/calendar/{date}` and `GET /api/v1/calendar/{date}`, including date normalization and not-found responses.
- [ ] Add UI tests for calculate date controls, Save persistence call, and calendar retrieval rendering.
- [ ] Add UI tests for missing-plan message and calculate-link navigation.
- [ ] Update README and canonical docs affected by new CLI command and persistent calendar behavior.
- [ ] Typecheck passes.
- [ ] Tests pass.

## 4. Functional Requirements

- FR-1: The system must persist meal plans by canonical date key `YYYYMMDD` in a JSON file.
- FR-2: The persistence store must auto-create when absent.
- FR-3: The persistence store must allow exactly one active meal plan per date key.
- FR-4: Writing a meal plan for an existing date key must overwrite prior value silently.
- FR-5: CLI `calculate` must require `--date` and validate it as `YYYYMMDD`.
- FR-6: After successful `calculate`, the produced meal plan must be saved under the provided date key.
- FR-7: CLI output rendering for `calculate` must continue to support `json|text|table`.
- FR-8: The system must provide a CLI `calendar` command.
- FR-9: CLI `calendar` must require `--date` in `YYYYMMDD` format.
- FR-10: CLI `calendar` must support `--format` values identical to `calculate`: `json|text|table`.
- FR-11: CLI `calendar` missing-date lookup must log an error and exit with code `3` (`ExitCode.DOMAIN`).
- FR-12: Web backend must provide `PUT /api/v1/calendar/{date}` to save date-keyed meal plans.
- FR-13: Web backend must provide `GET /api/v1/calendar/{date}` to retrieve date-keyed meal plans.
- FR-14: Web endpoint date values must be date-only and canonicalized to `YYYYMMDD`.
- FR-15: Web UI settings defaults must include `activity`, `training_before`, and `training_tomorrow`.
- FR-16: These settings defaults must use the same enum option sets as calculate inputs.
- FR-17: Web UI calculate screen must include date picker with `"<"` and `">"` day-step controls.
- FR-18: Calculate date control must initialize to current date.
- FR-19: Calculate Save action must persist the current meal plan for selected date.
- FR-20: Web UI must include top-level `Calendar` navigation entry and view.
- FR-21: Calendar view must include date picker with `"<"` and `">"` and initialize to current date.
- FR-22: Calendar view lookup must retrieve from backend using canonical `YYYYMMDD`.
- FR-23: Calendar view must render meal plan details read-only, without `+100/-100` controls.
- FR-24: Calendar view not-found state must show exact message `No meal plan exists, you first need to calculate one`.
- FR-25: In not-found message, `calculate` must link to calculate view.
- FR-26: Browser locale-specific date display formatting is allowed.
- FR-27: Time-of-day input must not be present in either calculate or calendar date controls.
- FR-28: Canonical API error response shape for UI-facing failures must be preserved.

## 5. Non-Goals (Out of Scope)

- Multi-user calendars, authentication, or remote sync.
- Any nutrition formula or macro allocation changes.
- Conflict warnings, version history, or merge behavior for same-date writes.
- Time-zone-aware multi-time persistence semantics beyond date-only behavior.
- Bulk calendar operations (range import/export/delete).
- Re-introducing mutable `+100/-100` adjustments on calendar display.

## 6. Design Considerations

- Keep date controls compact and aligned with existing calculate header row.
- Reuse existing calculate results visual components for calendar read-only display where possible.
- Preserve style-guide alignment and avoid introducing new visual patterns unnecessarily.
- Keep navigation parity across pages: `Settings`, `Calculate`, `Calendar`.

## 7. Technical Considerations

- Use file-backed JSON storage to minimize infrastructure complexity.
- Encapsulate storage I/O behind an adapter/service to avoid scattering file logic across CLI and web handlers.
- Enforce canonical `YYYYMMDD` parsing at entry boundaries (CLI and web API).
- Keep API contracts explicit so UI can distinguish not-found from other failures.
- Preserve existing canonical error-code mapping patterns and exit-code mapping conventions.

## 8. Success Metrics

- Users can save and retrieve daily meal plans from both CLI and web UI.
- Same-date writes reliably overwrite prior plans.
- Calendar retrieval works with canonical `YYYYMMDD` across all interfaces.
- Missing-plan behavior is deterministic in CLI (error + exit code `3`) and clear in UI (required message + calculate link).
- All new tests for persistence, retrieval, date handling, and UI navigation pass.

## 9. Open Questions

- None for this enhancement scope after clarifications.

## 10. Implementation Backlog (Enhance-005)

### Phase A: Core Persistence and Date Canonicalization

1. Add file-backed JSON meal-plan calendar storage adapter keyed by `YYYYMMDD`.
2. Add canonical date parsing/validation utility shared by CLI and web adapters.
3. Add overwrite and missing-date behaviors with deterministic error pathways.

### Phase B: CLI Integration

1. Extend `calculate` with required `--date` and persistence write on success.
2. Add `calendar` command with `--date`, `--format`, and help wiring.
3. Align output formats to `json|text|table` across both commands.
4. Implement missing-date CLI failure with logged error and exit code `3`.

### Phase C: Web API Integration

1. Add `PUT /api/v1/calendar/{date}` to write persisted meal plans by date.
2. Add `GET /api/v1/calendar/{date}` to read persisted meal plans by date.
3. Ensure canonical date normalization and consistent API error responses.

### Phase D: Web UI Updates

1. Add date picker + day-step controls to `Calculate` header row.
2. Add date-only handling and `YYYYMMDD` conversion before backend requests.
3. Wire calculate-results `Save` to backend persistence write for selected date.
4. Add settings defaults for `activity`, `training_before`, and `training_tomorrow` with local-storage persistence.
5. Add top-level `Calendar` view with date navigation and backend lookup.
6. Render stored calendar plan read-only and remove/omit `+100/-100` controls.
7. Implement missing-plan UI message with linked `calculate` navigation.

### Phase E: Hardening and Documentation

1. Add/extend CLI, API, and UI tests for date behavior, overwrite semantics, and not-found handling.
2. Update user and architecture documentation for persistent calendar workflows.
3. Run and pass quality gates: typecheck and tests.
