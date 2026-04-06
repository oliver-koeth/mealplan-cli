# PRD: Enhance-004 Calculate UI

## 1. Introduction/Overview

This enhancement adds the first local browser UI for meal-plan calculation. Today the project is CLI-only, which makes repeated use cumbersome because users must repeatedly enter athlete profile values and day-specific training inputs through command-line flags, including a JSON string for training zones. The new UI introduces a style-guide-aligned web workflow that separates stable athlete settings from day-specific inputs, persists current values in browser local storage, submits the combined payload to a local calculate API, and renders the returned plan in a dedicated panel-like results view state inside the calculate screen.

The enhancement must preserve the existing Python calculation engine as the single source of nutrition logic. The browser UI is a presentation layer only. It collects inputs, calls the local REST endpoint, and renders the canonical response. The results view state also adds display-only scaling in `100 kcal` increments so users can inspect proportionally adjusted meal plans without recalculating on the server.

## 2. Goals

- Add a local web UI for the existing `calculate` workflow.
- Keep the Python application service as the canonical calculation engine.
- Introduce a `Settings` page for stable athlete inputs.
- Introduce a `Calculate` page for day-specific inputs.
- Persist current form values in browser local storage so the UI restores prior inputs.
- Replace JSON-based training-zone entry in the browser with separate minute inputs for zones `1..5`.
- Expose a local `POST /api/v1/calculate` endpoint for the browser flow.
- Render returned totals and meal details in a style-guide-aligned results panel-like view state inside `Calculate`.
- Allow display-only scaling of the returned plan in signed `100 kcal` steps with proportional meal adjustment.
- Keep the first `Save` interaction intentionally simple: close/dismiss the results state and return to the calculate input state without persistence.

## 3. User Stories

### US-001: Start local UI mode and serve the web application shell
**Description:** As a local user, I want `mealplan --ui` to start a browser-accessible app shell so that I can use meal-plan calculation without assembling CLI flags manually.

**Acceptance Criteria:**
- [ ] The CLI accepts a root-level `--ui` mode that starts the local web server instead of running a one-off calculation.
- [ ] UI mode binds to loopback and prints the local URL for manual opening.
- [ ] UI mode binds specifically to `127.0.0.1` by default.
- [ ] UI mode prefers port `8765`; when occupied, it probes `8766..8775` sequentially and uses the first free port.
- [ ] If all ports in `8765..8775` are occupied, startup fails with clear messaging and non-zero exit.
- [ ] Startup output includes:
- [ ] `UI available at http://127.0.0.1:<port>/calculate`
- [ ] `Health endpoint: http://127.0.0.1:<port>/api/v1/health`
- [ ] UI mode never auto-launches a browser.
- [ ] On `SIGINT`/`SIGTERM`, the server stops accepting new requests immediately, drains in-flight requests up to `5` seconds, then exits with code `0`.
- [ ] The same server process serves the browser app shell and API routes.
- [ ] The browser app shell loads successfully from the local server in both light and dark themes.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-002: Expose the calculate API through the local web adapter
**Description:** As the web UI, I want a local calculate endpoint that reuses the existing application service so that browser requests return the same canonical meal-plan response as the CLI.

**Acceptance Criteria:**
- [ ] Add `POST /api/v1/calculate` on the local web server.
- [ ] The endpoint accepts the canonical `MealPlanRequest` JSON shape used by the application layer.
- [ ] The endpoint returns the canonical `MealPlanResponse` JSON shape on success.
- [ ] Validation failures map to HTTP `400`, domain rule violations map to HTTP `422`, and unexpected failures map to HTTP `500`.
- [ ] Error responses use the canonical JSON shape `{ "error": { "code": string, "message": string, "details"?: [{ "field"?: string, "message": string }], "request_id": string } }`.
- [ ] Error codes are fixed as `validation_error`, `domain_rule_error`, and `internal_error` for HTTP `400`, `422`, and `500` respectively.
- [ ] The web adapter calls the in-process application service directly and does not shell out to the CLI.
- [ ] Add `GET /api/v1/health` for deterministic local health checks.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Provide a style-guide-aligned web app shell and navigation
**Description:** As a user, I want the web UI to feel like the documented product style so that the new workflow is trustworthy, compact, and easy to scan.

**Acceptance Criteria:**
- [ ] The app uses the neutral card-based shell defined in `docs/STYLEGUIDE.md`.
- [ ] The UI has a compact sticky header with product title and navigation between `Settings` and `Calculate`.
- [ ] Theme tokens, spacing, borders, and buttons follow the documented style-guide direction.
- [ ] The layout works as a single-column stack on mobile and keeps forms readable on larger screens.
- [ ] The app shell supports both light and dark mode without changing component structure.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-004: Capture stable athlete settings with local storage restore
**Description:** As a repeat user, I want stable athlete settings stored separately and restored automatically so that I do not have to re-enter profile data each time I open the UI.

**Acceptance Criteria:**
- [ ] The `Settings` page includes controls for `age`, `gender`, `height`, `weight`, `vo2max`, and `carbs`.
- [ ] Numeric fields use numeric inputs and enum-like fields use dropdowns.
- [ ] `vo2max` is optional in the UI.
- [ ] Current settings-page values are persisted to browser local storage whenever they change.
- [ ] Reloading the app restores the latest stored settings-page values into the form.
- [ ] The page uses grouped, low-noise form cards consistent with the style guide.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-005: Capture day-specific calculation inputs with type-appropriate controls
**Description:** As a user planning a specific day, I want a calculate form with day-only inputs and explicit zone-minute fields so that I can enter the day’s training context without JSON or guesswork.

**Acceptance Criteria:**
- [ ] The `Calculate` page includes controls for `activity`, `training_tomorrow`, `training_before`, and separate minute fields for zones `1`, `2`, `3`, `4`, and `5`.
- [ ] `activity`, `training_tomorrow`, and `training_before` are dropdowns.
- [ ] Zone inputs accept integer minutes only and are displayed as separate fields, not a JSON textarea.
- [ ] Current calculate-page values are persisted to browser local storage whenever they change.
- [ ] Reloading the app restores the latest stored calculate-page values into the form.
- [ ] If all zone minutes are `0`, submit readiness does not require `training_before`.
- [ ] If any zone minutes are greater than `0`, the UI requires `training_before` before submission and shows concise inline guidance.
- [ ] The UI does not expose the semantically invalid CLI-only value `training_before=training`.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-006: Submit combined settings and day inputs to the calculate API
**Description:** As a user, I want the calculate action to combine both forms and call the local API so that one click produces a meal plan from all current inputs.

**Acceptance Criteria:**
- [ ] The `Calculate` page includes a `Calculate` button as the primary action.
- [ ] Clicking `Calculate` assembles the canonical request payload from both the settings page and calculate page values.
- [ ] Zone minute inputs are mapped to `training_session.zones_minutes` with canonical keys `1..5`.
- [ ] When submission succeeds, the UI opens the in-page panel-like results view state with the returned payload.
- [ ] While the request is in flight, the UI shows a restrained loading state and prevents duplicate submissions.
- [ ] Validation and API errors are rendered inline in concise card or panel form consistent with the style guide.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-007: Render the meal-plan results panel state with totals and meal cards
**Description:** As a user, I want a dedicated panel-like results view state inside calculate that shows the returned plan clearly so that I can review totals and meal details without leaving the calculate workflow.

**Acceptance Criteria:**
- [ ] Successful calculation opens a dedicated panel-like results view state layered within the calculate workflow.
- [ ] The results view shows top-level totals from the API response, including `TDEE`, `training_kcal`, `protein_g`, `carbs_g`, `fat_g`, and `total_kcal`.
- [ ] Meals are rendered in canonical order using simple cards or rows aligned with the style guide.
- [ ] Each meal shows the returned meal name, carb strategy, calories, and macro values.
- [ ] The view includes a back button that closes results and returns to the input page without clearing stored form values.
- [ ] Results cannot be directly navigated to by route/URL entry and are only available after a successful calculate submit.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-008: Add display-only kcal scaling and placeholder save behavior
**Description:** As a user, I want to inspect the plan at slightly higher or lower calorie totals so that I can evaluate simple adjustments before a real save/export workflow exists.

**Acceptance Criteria:**
- [ ] The results view includes controls to increase or decrease displayed daily total kcal in signed `100 kcal` steps.
- [ ] The returned API `total_kcal` is the fixed baseline for scaling calculations.
- [ ] Changing the displayed total proportionally rescales displayed meal calories, displayed meal macros, and displayed top-level macros.
- [ ] Scaling is deterministic and uses presentation-layer rounding only.
- [ ] After display rounding, a tolerance of up to `1%` is acceptable between displayed scaled totals and the sums of displayed scaled meals/macros.
- [ ] The results view includes a `Save` button that currently performs no persistence and dismisses results state, returning to calculate input state.
- [ ] Returning from the results view preserves the current stored form inputs.
- [ ] After `Save`, the current results state is cleared and remains hidden until a new calculation is triggered.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

### US-009: Keep web UI tests, packaging, and canonical docs aligned
**Description:** As a maintainer, I want the new UI workflow documented and regression-tested so that the web adapter and browser flow remain stable after rollout.

**Acceptance Criteria:**
- [ ] Add automated coverage for the local web adapter and calculate API behavior.
- [ ] Add automated UI-shell coverage for settings restore, calculate-form submission, results rendering, and scaling behavior.
- [ ] Installed UI mode runs via the Python package without requiring a separate frontend runtime.
- [ ] Development workflow is documented as the Python `mealplan --ui` flow with local REST API served in-process.
- [ ] User-facing launch docs describe the `Settings`/`Calculate` routes and local API routes.
- [ ] Update `docs/ARCHITECTURE.md`, `docs/REQUIREMENTS.md`, `docs/PLAN.md`, and any user-facing launch documentation to describe the new UI/API workflow.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in local browser.

## 4. Functional Requirements

- FR-1: The system must provide a local browser-accessible UI mode started from the CLI.
- FR-2: UI mode must be served by the same local process that exposes the REST API.
- FR-3: The system must provide `POST /api/v1/calculate`.
- FR-4: The system must provide `GET /api/v1/health`.
- FR-5: `POST /api/v1/calculate` must accept the canonical `MealPlanRequest` JSON shape.
- FR-6: `POST /api/v1/calculate` must return the canonical `MealPlanResponse` JSON shape on success.
- FR-7: API error responses must use `{ "error": { "code": string, "message": string, "details"?: [{ "field"?: string, "message": string }], "request_id": string } }`.
- FR-8: HTTP `400`, `422`, and `500` must map to `validation_error`, `domain_rule_error`, and `internal_error` respectively.
- FR-9: The web adapter must call the application service directly in-process and must not invoke the CLI as a subprocess.
- FR-10: The UI must include navigation between `Settings` and `Calculate`.
- FR-11: The `Settings` page must capture `age`, `gender`, `height`, `weight`, `vo2max`, and `carbs`.
- FR-12: The `Calculate` page must capture `activity`, `training_tomorrow`, `training_before`, and zones `1..5` minutes.
- FR-13: Numeric values must use numeric controls.
- FR-14: `gender`, `activity`, `carbs`, `training_tomorrow`, and `training_before` must use dropdown controls.
- FR-15: The UI must persist current settings-page values to browser local storage.
- FR-16: The UI must persist current calculate-page values to browser local storage.
- FR-17: The UI must restore stored form values on reload or later return.
- FR-18: Zone inputs must map to `training_session.zones_minutes` with canonical keys `1..5`.
- FR-19: If all zone minutes are `0`, `training_before` may be omitted from submission.
- FR-20: If any zone minutes are greater than `0`, the UI must require `training_before` before submission.
- FR-21: The UI must not expose `training_before=training`.
- FR-22: The `Calculate` page must provide a `Calculate` primary action.
- FR-23: The calculate action must combine data from both pages into one canonical request payload.
- FR-24: The UI must show restrained inline loading and error states.
- FR-25: Successful calculation must open a dedicated panel-like results view state within the `Calculate` screen.
- FR-26: The results view must show top-level totals and meal-by-meal details from the API response.
- FR-27: The results view must include a back action that returns to the input page.
- FR-28: The results view must provide `100 kcal` increment and decrement controls for display-only scaling.
- FR-29: Scaling must use the returned `total_kcal` as the baseline.
- FR-30: Scaling must proportionally adjust displayed meal calories, displayed meal macros, and displayed top-level macros.
- FR-31: After display rounding, scaled totals may differ from displayed meal/macro sums by at most `1%`.
- FR-32: The results view must include a `Save` action that currently dismisses results state and returns to calculate input state without persistence.
- FR-33: Results state must not be directly navigable via route/URL entry.
- FR-34: Results state must be visible only after a successful calculate action and must be cleared after `Save`.
- FR-35: The UI must follow the visual direction defined in `docs/STYLEGUIDE.md`.
- FR-36: The UI must support both light and dark themes.
- FR-37: Installed UI mode must not require a separate manually started frontend runtime in production usage.
- FR-38: Development workflow must support running the UI via `mealplan --ui` with local API routes served in-process.
- FR-39: User-facing launch documentation must describe `Settings`/`Calculate` UI routes and `/api/v1/health` plus `/api/v1/calculate`.
- FR-40: CI/install smoke validation must include packaged UI-mode startup and local API health checks.
- FR-41: UI mode server bind host must default to `127.0.0.1`.
- FR-42: UI mode server must prefer port `8765`.
- FR-43: On collision at `8765`, UI mode server must probe `8766..8775` sequentially and bind the first free port.
- FR-44: If no free port exists in `8765..8775`, startup must fail with clear messaging and non-zero exit.
- FR-45: UI-mode startup output must include canonical UI URL and health endpoint URL lines.
- FR-46: UI mode must not auto-launch a browser.
- FR-47: UI mode must handle `SIGINT` and `SIGTERM` with graceful shutdown, including a `5` second in-flight request drain window.
- FR-48: UI mode must exit with status `0` on normal signal-triggered graceful shutdown.

## 5. Non-Goals (Out of Scope)

- Changing meal-planning formulas or domain rules.
- Adding user accounts, cloud sync, or multi-user state.
- Persisting results on the server or in the browser beyond current input values.
- Implementing a real save/export/share workflow.
- Supporting CLI-only runtime/output flags such as `--format` or `--debug` in the web UI.
- Adding additional business flows beyond the current calculate use case.
- Introducing browser-side calculation logic that duplicates Python domain rules.

## 6. Design Considerations

- Follow `docs/STYLEGUIDE.md` closely: compact sticky header, section cards, restrained forms, semantic nutrition colors, and simple result presentation.
- Keep forms plain and legible with labels above controls and grouped cards instead of dense, unstructured inputs.
- Keep the settings screen narrow and low-noise.
- Keep the results screen focused on scannable totals and meal cards rather than decorative data visualization.
- Treat scaling as a display affordance on top of the returned result, not as a second backend calculation path.
- Preserve canonical meal ordering in the results view.

## 7. Technical Considerations

- The enhancement introduces both a local web adapter and the first browser UI, so backend and frontend stories must be dependency-ordered.
- The server should expose structured HTTP error responses so the UI can render concise inline errors.
- The canonical error shape for this enhancement is `{ "error": { "code": string, "message": string, "details"?: [{ "field"?: string, "message": string }], "request_id": string } }`.
- The browser should store only input state in local storage; result payload persistence is explicitly out of scope.
- The app must bridge the current CLI/application request contract to a browser-friendly form model, especially for separate zone-minute fields.
- `height` belongs on the `Settings` page even though it was not explicitly listed in the original request examples, because it is a required stable athlete input in the canonical request contract.
- Runtime packaging must support installed UI usage without a separate frontend server process.
- Chosen workflow is single-process Python UI serving for both development and installed runtime.

## 8. Success Metrics

- A user can complete meal-plan calculation end to end through the browser without using CLI flags.
- Returning to the UI restores the user’s most recent input values from local storage.
- Training-zone entry in the browser is done through separate zone fields rather than JSON text.
- The browser UI uses the canonical API and returns the same structured response semantics as the CLI path.
- The results panel state clearly presents totals and meals, is entered only after calculate submit, and supports deterministic `100 kcal` scaling with scaled top-level macros and a 1% rounding tolerance.
- Type checking, automated tests, and local browser verification pass for the delivered workflow.

## 9. Open Questions

- None for the current enhancement scope. The enhancement brief already resolves the main scope boundaries, including display-only scaling and placeholder save behavior.

## 10. Implementation Backlog (Enhance-004)

### Phase A: Local Web Adapter

1. Add local `--ui` startup mode and serve the web application shell from the same process.
2. Implement fixed UI server lifecycle contract: host `127.0.0.1`, preferred port `8765`, collision fallback `8766..8775`, clear startup failure when exhausted.
3. Implement canonical startup output lines for UI and health URLs.
4. Implement graceful shutdown handling for `SIGINT`/`SIGTERM` with `5` second in-flight drain and exit code `0`.
5. Add `GET /api/v1/health`.
6. Add `POST /api/v1/calculate` using the canonical application request/response DTOs.
7. Map validation, domain, and unexpected failures to structured HTTP error responses.

### Phase B: UI Foundation

1. Scaffold the browser application shell with sticky header, navigation, theme support, and style-guide-aligned base tokens.
2. Ensure the shell runs from the local Python-served route rather than from a separate manually started runtime in production mode.

### Phase C: Settings and Calculate Input Flow

1. Build the `Settings` page with stable athlete inputs and local-storage persistence.
2. Build the `Calculate` page with day-specific inputs, separate zone-minute fields, and local-storage persistence.
3. Add submit-readiness rules for `training_before` based on entered zone minutes.
4. Combine settings and day inputs into the canonical request payload on calculate.

### Phase D: Results Workflow

1. Open a dedicated panel-like results view state after successful calculation from the calculate input state.
2. Render totals and meal cards in canonical order using style-guide-aligned components.
3. Add back navigation from results to the calculate page.
4. Add display-only signed `100 kcal` scaling with proportional meal adjustment.
5. Ensure results is not directly routable and is cleared after `Save`.
6. Add placeholder `Save` behavior that closes results and returns to the calculate input state.

### Phase E: Hardening and Documentation

1. Add automated tests for local web adapter and UI-shell browser-flow behavior.
2. Add local browser verification coverage for the key UI stories.
3. Validate packaged local runtime usage through `mealplan --ui` install-smoke checks.
4. Implement and document the Python single-process dev workflow (`mealplan --ui`).
5. Update canonical docs and launch guidance for the new UI/API workflow.
6. Run full quality gates: typecheck and tests.
