"""Local UI mode HTTP server lifecycle and routing."""

from __future__ import annotations

import json
import os
import signal
import socketserver
import threading
import time
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from string import Template
from uuid import uuid4

from mealplan.application.contracts import MealPlanRequest
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.shared.errors import DomainRuleError, ValidationError

UI_HOST = "127.0.0.1"
UI_PORT_START = 8765
UI_PORT_END = 8775
SHUTDOWN_DRAIN_SECONDS = 5.0
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"

_APP_SHELL_TEMPLATE = Template("""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mealplan UI</title>
    <style>
      :root {
        color-scheme: light dark;
        --canvas: #f8fafc;
        --surface: #ffffff;
        --surface-muted: #f1f5f9;
        --border: #e2e8f0;
        --text: #1e293b;
        --text-muted: #475569;
        --text-subtle: #64748b;
        --shadow: rgba(15, 23, 42, 0.06);
        --header: rgba(248, 250, 252, 0.9);
        --link-active: #0f172a;
      }

      @media (prefers-color-scheme: dark) {
        :root {
          --canvas: #020617;
          --surface: #0f172a;
          --surface-muted: #1e293b;
          --border: #1f2937;
          --text: #e2e8f0;
          --text-muted: #cbd5e1;
          --text-subtle: #94a3b8;
          --shadow: rgba(2, 6, 23, 0.5);
          --header: rgba(2, 6, 23, 0.85);
          --link-active: #f8fafc;
        }
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(14, 165, 233, 0.1), transparent 45%),
          var(--canvas);
      }

      .app-header {
        position: sticky;
        top: 0;
        z-index: 10;
        backdrop-filter: blur(8px);
        border-bottom: 1px solid var(--border);
        background: var(--header);
      }

      .header-inner {
        max-width: 1280px;
        margin: 0 auto;
        padding: 0.75rem 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        flex-wrap: wrap;
      }

      .brand {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
      }

      .brand strong {
        font-size: 1rem;
        font-weight: 600;
      }

      .brand span {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-subtle);
      }

      nav {
        display: flex;
        gap: 0.25rem;
      }

      .nav-link {
        text-decoration: none;
        color: var(--text-muted);
        font-size: 0.88rem;
        padding: 0.35rem 0.6rem;
        border-radius: 999px;
        border: 1px solid transparent;
      }

      .nav-link[aria-current="page"] {
        color: var(--link-active);
        border-color: var(--border);
        background: var(--surface);
        font-weight: 600;
      }

      .shell {
        max-width: 1280px;
        margin: 0 auto;
        padding: 1rem;
      }

      .stack {
        max-width: 880px;
        margin: 0 auto;
        display: grid;
        gap: 0.75rem;
      }

      .card {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--surface);
        box-shadow: 0 1px 2px var(--shadow);
        padding: 1rem;
      }

      .section-label {
        margin: 0;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--text-subtle);
      }

      h1 {
        margin: 0.45rem 0 0;
        font-size: 1.15rem;
      }

      p {
        margin: 0.75rem 0 0;
        color: var(--text-muted);
        line-height: 1.45;
        font-size: 0.92rem;
      }

      .grid {
        display: grid;
        gap: 0.75rem;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .muted-card {
        border-radius: 10px;
        background: var(--surface-muted);
        border: 1px solid var(--border);
        padding: 0.75rem;
      }

      .muted-card h2 {
        margin: 0;
        font-size: 0.88rem;
      }

      .muted-card p {
        margin-top: 0.35rem;
        font-size: 0.82rem;
      }

      .form-stack {
        display: grid;
        gap: 0.75rem;
      }

      .form-card {
        border-radius: 10px;
        border: 1px solid var(--border);
        background: var(--surface-muted);
        padding: 0.85rem;
      }

      .form-card h2 {
        margin: 0;
        font-size: 0.9rem;
      }

      .field-grid {
        margin-top: 0.65rem;
        display: grid;
        gap: 0.65rem;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      label {
        display: grid;
        gap: 0.35rem;
        font-size: 0.82rem;
        color: var(--text-muted);
      }

      input,
      select {
        width: 100%;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--text);
        font: inherit;
        padding: 0.45rem 0.55rem;
      }

      .actions {
        margin-top: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.55rem;
        flex-wrap: wrap;
      }

      .primary-button {
        border: 1px solid var(--border);
        border-radius: 9px;
        background: var(--surface);
        color: var(--text);
        padding: 0.5rem 0.8rem;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }

      .primary-button[disabled] {
        cursor: wait;
        opacity: 0.7;
      }

      .status-note {
        font-size: 0.78rem;
        color: var(--text-subtle);
      }

      .alert-card {
        border-radius: 10px;
        border: 1px solid #dc2626;
        background: rgba(220, 38, 38, 0.1);
        padding: 0.75rem;
      }

      .alert-card h2 {
        margin: 0;
        font-size: 0.86rem;
      }

      .alert-card p,
      .alert-card ul {
        margin: 0.45rem 0 0;
        color: var(--text-muted);
        font-size: 0.82rem;
      }

      .alert-card ul {
        padding-left: 1rem;
      }

      .results-panel pre {
        margin: 0.55rem 0 0;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--surface-muted);
        padding: 0.65rem;
        overflow-x: auto;
        font-size: 0.76rem;
      }

      .hint {
        margin: 0.65rem 0 0;
        color: var(--text-subtle);
        font-size: 0.78rem;
      }

      @media (max-width: 720px) {
        .shell {
          padding: 0.75rem;
        }

        .grid {
          grid-template-columns: 1fr;
        }

        .field-grid {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <header class="app-header">
      <div class="header-inner">
        <div class="brand">
          <strong>Mealplan</strong>
          <span>Local UI</span>
        </div>
        <nav aria-label="Primary">
          <a class="nav-link" href="/settings" aria-current="$settings_current">Settings</a>
          <a class="nav-link" href="/calculate" aria-current="$calculate_current">Calculate</a>
        </nav>
      </div>
    </header>
    <main class="shell">
      <section class="stack">
        <article class="card">
          <p class="section-label">$section_label</p>
          <h1>$title</h1>
          <p>$description</p>
        </article>
        <article class="card">
          $content_html
        </article>
      </section>
    </main>
    <script>
      (() => {
        const settingsStorageKey = "mealplan.ui.settings.v1";
        const calculateStorageKey = "mealplan.ui.calculate.v1";

        const readLocalStorageObject = (storageKey) => {
          const raw = window.localStorage.getItem(storageKey);
          if (!raw) {
            return {};
          }
          try {
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
              return {};
            }
            return parsed;
          } catch {
            return {};
          }
        };

        const bindLocalStorageForm = (form, storageKey, fields) => {
          if (!form) {
            return;
          }

          const readValues = () => {
            const result = {};
            for (const name of fields) {
              const control = form.elements.namedItem(name);
              if (control && "value" in control) {
                result[name] = control.value;
              }
            }
            return result;
          };

          const restoreValues = () => {
            const parsed = readLocalStorageObject(storageKey);
            for (const name of fields) {
              const control = form.elements.namedItem(name);
              const value = parsed[name];
              if (control && "value" in control && typeof value === "string") {
                control.value = value;
              }
            }
          };

          const persistValues = () => {
            window.localStorage.setItem(storageKey, JSON.stringify(readValues()));
          };

          restoreValues();
          form.addEventListener("input", persistValues);
          form.addEventListener("change", persistValues);
        };

        const readFormValues = (form, fields) => {
          if (!form) {
            return {};
          }
          const result = {};
          for (const name of fields) {
            const control = form.elements.namedItem(name);
            if (control && "value" in control) {
              result[name] = control.value;
            }
          }
          return result;
        };

        const parseIntegerOrNull = (rawValue) => {
          const parsed = Number.parseInt(rawValue ?? "", 10);
          if (!Number.isFinite(parsed)) {
            return null;
          }
          return parsed;
        };

        const parseNumberOrNull = (rawValue) => {
          const parsed = Number.parseFloat(rawValue ?? "");
          if (!Number.isFinite(parsed)) {
            return null;
          }
          return parsed;
        };

        const settingsForm = document.querySelector('[data-settings-form="true"]');
        bindLocalStorageForm(settingsForm, settingsStorageKey, [
          "age",
          "gender",
          "height_cm",
          "weight_kg",
          "vo2max",
          "carb_mode",
        ]);

        const calculateForm = document.querySelector('[data-calculate-form="true"]');
        bindLocalStorageForm(calculateForm, calculateStorageKey, [
          "activity_level",
          "training_load_tomorrow",
          "training_before_meal",
          "zone_1_minutes",
          "zone_2_minutes",
          "zone_3_minutes",
          "zone_4_minutes",
          "zone_5_minutes",
        ]);
        if (!calculateForm) {
          return;
        }

        const zoneFieldNames = [
          "zone_1_minutes",
          "zone_2_minutes",
          "zone_3_minutes",
          "zone_4_minutes",
          "zone_5_minutes",
        ];
        const trainingBeforeControl = calculateForm.elements.namedItem("training_before_meal");
        const guidance = document.querySelector('[data-training-before-guidance="true"]');
        if (!trainingBeforeControl || !("value" in trainingBeforeControl)) {
          return;
        }

        const calculateButton = calculateForm.querySelector('[data-calculate-submit="true"]');
        const statusNote = document.querySelector('[data-calculate-status="true"]');
        const errorCard = document.querySelector('[data-calculate-error-card="true"]');
        const errorSummary = document.querySelector('[data-calculate-error-summary="true"]');
        const errorList = document.querySelector('[data-calculate-error-list="true"]');
        const resultsPanel = document.querySelector('[data-calculate-results="true"]');
        const resultsJson = document.querySelector('[data-calculate-results-json="true"]');
        let requestInFlight = false;

        const parseMinutes = (rawValue) => {
          const parsed = parseIntegerOrNull(rawValue);
          if (parsed === null || parsed < 0) {
            return 0;
          }
          return parsed;
        };

        const hasTrainingVolume = () => {
          for (const fieldName of zoneFieldNames) {
            const control = calculateForm.elements.namedItem(fieldName);
            if (!control || !("value" in control)) {
              continue;
            }
            if (parseMinutes(control.value) > 0) {
              return true;
            }
          }
          return false;
        };

        const updateTrainingBeforeRequirement = () => {
          if (hasTrainingVolume()) {
            trainingBeforeControl.required = true;
            if (!trainingBeforeControl.value) {
              trainingBeforeControl.setCustomValidity(
                "Select a meal timing when zone minutes are greater than zero."
              );
              if (guidance) {
                guidance.hidden = false;
              }
              return;
            }
          } else {
            trainingBeforeControl.required = false;
          }

          trainingBeforeControl.setCustomValidity("");
          if (guidance) {
            guidance.hidden = true;
          }
        };

        const renderApiError = (errorPayload) => {
          if (!errorCard) {
            return;
          }
          if (errorSummary) {
            errorSummary.textContent = errorPayload.message ?? "Calculation failed.";
          }
          if (errorList) {
            errorList.innerHTML = "";
            const details = Array.isArray(errorPayload.details) ? errorPayload.details : [];
            for (const detail of details) {
              const item = document.createElement("li");
              if (detail && typeof detail === "object") {
                const field = typeof detail.field === "string" ? detail.field : "";
                const message = (
                  typeof detail.message === "string"
                    ? detail.message
                    : "Invalid value."
                );
                item.textContent = field ? field + ": " + message : message;
              } else {
                item.textContent = "Invalid request.";
              }
              errorList.appendChild(item);
            }
            errorList.hidden = errorList.children.length === 0;
          }
          errorCard.hidden = false;
        };

        const clearApiFeedback = () => {
          if (errorCard) {
            errorCard.hidden = true;
          }
          if (resultsPanel) {
            resultsPanel.hidden = true;
          }
        };

        const setSubmissionState = (inFlight) => {
          requestInFlight = inFlight;
          if (calculateButton) {
            calculateButton.disabled = inFlight;
            calculateButton.textContent = inFlight ? "Calculating..." : "Calculate";
          }
          if (statusNote) {
            statusNote.textContent = inFlight ? "Submitting request..." : "";
          }
        };

        const createRequestPayload = () => {
          const settingsSnapshot = {
            ...readLocalStorageObject(settingsStorageKey),
            ...readFormValues(settingsForm, [
              "age",
              "gender",
              "height_cm",
              "weight_kg",
              "vo2max",
              "carb_mode",
            ]),
          };
          const calculateSnapshot = {
            ...readLocalStorageObject(calculateStorageKey),
            ...readFormValues(calculateForm, [
              "activity_level",
              "training_load_tomorrow",
              "training_before_meal",
              "zone_1_minutes",
              "zone_2_minutes",
              "zone_3_minutes",
              "zone_4_minutes",
              "zone_5_minutes",
            ]),
          };

          const requestPayload = {
            age: parseIntegerOrNull(settingsSnapshot.age),
            gender: settingsSnapshot.gender ?? "",
            height_cm: parseIntegerOrNull(settingsSnapshot.height_cm),
            weight_kg: parseNumberOrNull(settingsSnapshot.weight_kg),
            carb_mode: settingsSnapshot.carb_mode ?? "",
            activity_level: calculateSnapshot.activity_level ?? "",
            training_session: {
              training_load_tomorrow: calculateSnapshot.training_load_tomorrow ?? "",
              training_before_meal: calculateSnapshot.training_before_meal || null,
              zones_minutes: {
                "1": parseMinutes(calculateSnapshot.zone_1_minutes),
                "2": parseMinutes(calculateSnapshot.zone_2_minutes),
                "3": parseMinutes(calculateSnapshot.zone_3_minutes),
                "4": parseMinutes(calculateSnapshot.zone_4_minutes),
                "5": parseMinutes(calculateSnapshot.zone_5_minutes),
              },
            },
          };

          const vo2max = parseNumberOrNull(settingsSnapshot.vo2max);
          if (vo2max !== null) {
            requestPayload.vo2max = vo2max;
          }
          return requestPayload;
        };

        const submitCalculation = async () => {
          if (requestInFlight) {
            return;
          }
          updateTrainingBeforeRequirement();
          if (!calculateForm.reportValidity()) {
            return;
          }

          clearApiFeedback();
          setSubmissionState(true);
          try {
            const response = await window.fetch("/api/v1/calculate", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify(createRequestPayload()),
            });
            const payload = await response.json();
            if (!response.ok) {
              renderApiError(payload.error ?? {});
              return;
            }
            if (resultsJson) {
              resultsJson.textContent = JSON.stringify(payload, null, 2);
            }
            if (resultsPanel) {
              resultsPanel.hidden = false;
            }
          } catch {
            renderApiError({message: "Unable to reach local calculate API."});
          } finally {
            setSubmissionState(false);
          }
        };

        updateTrainingBeforeRequirement();
        calculateForm.addEventListener("input", updateTrainingBeforeRequirement);
        calculateForm.addEventListener("change", updateTrainingBeforeRequirement);
        calculateForm.addEventListener("submit", (event) => {
          event.preventDefault();
          void submitCalculation();
        });
      })();
    </script>
  </body>
</html>
""")


_PAGE_CONTENT: dict[str, dict[str, str]] = {
    "settings": {
        "section_label": "Settings",
        "title": "Athlete profile and defaults",
        "description": (
            "Capture stable profile details here. Calculation inputs and meal-plan results are "
            "managed separately on the calculate page."
        ),
        "content_html": """
          <p class="section-label">Athlete Settings</p>
          <form class="form-stack" data-settings-form="true">
            <section class="form-card">
              <h2>Profile</h2>
              <div class="field-grid">
                <label>Age
                  <input name="age" type="number" min="1" step="1" required />
                </label>
                <label>Gender
                  <select name="gender" required>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </label>
                <label>Height (cm)
                  <input name="height_cm" type="number" min="1" step="1" required />
                </label>
                <label>Weight (kg)
                  <input name="weight_kg" type="number" min="1" step="0.1" required />
                </label>
              </div>
            </section>
            <section class="form-card">
              <h2>Planning Defaults</h2>
              <div class="field-grid">
                <label>VO2max (optional)
                  <input name="vo2max" type="number" min="10" max="100" step="1" />
                </label>
                <label>Carbs
                  <select name="carb_mode" required>
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="periodized">Periodized</option>
                  </select>
                </label>
              </div>
            </section>
          </form>
          <p class="hint">Settings are saved automatically in this browser.</p>
        """,
    },
    "calculate": {
        "section_label": "Calculate",
        "title": "Daily training and meal-plan calculation",
        "description": (
            "Use this page for day-specific training context and run the meal-plan "
            "calculation against your saved settings."
        ),
        "content_html": """
          <p class="section-label">Day Inputs</p>
          <form class="form-stack" data-calculate-form="true">
            <section class="form-card">
              <h2>Training Context</h2>
              <div class="field-grid">
                <label>Activity
                  <select name="activity_level" required>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <label>Tomorrow Training Load
                  <select name="training_load_tomorrow" required>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <label>Training Before Meal
                  <select name="training_before_meal">
                    <option value="">No training meal timing</option>
                    <option value="breakfast">Breakfast</option>
                    <option value="morning-snack">Morning snack</option>
                    <option value="lunch">Lunch</option>
                    <option value="afternoon-snack">Afternoon snack</option>
                    <option value="dinner">Dinner</option>
                    <option value="evening-snack">Evening snack</option>
                  </select>
                </label>
              </div>
              <p class="hint" data-training-before-guidance="true" hidden>
                Select training-before timing whenever any zone minutes are above 0.
              </p>
            </section>
            <section class="form-card">
              <h2>Zones Minutes</h2>
              <div class="field-grid">
                <label>Zone 1 Minutes
                  <input name="zone_1_minutes" type="number" min="0" step="1" value="0" required />
                </label>
                <label>Zone 2 Minutes
                  <input name="zone_2_minutes" type="number" min="0" step="1" value="0" required />
                </label>
                <label>Zone 3 Minutes
                  <input name="zone_3_minutes" type="number" min="0" step="1" value="0" required />
                </label>
                <label>Zone 4 Minutes
                  <input name="zone_4_minutes" type="number" min="0" step="1" value="0" required />
                </label>
                <label>Zone 5 Minutes
                  <input name="zone_5_minutes" type="number" min="0" step="1" value="0" required />
                </label>
              </div>
            </section>
            <div class="actions">
              <button class="primary-button" type="submit" data-calculate-submit="true">
                Calculate
              </button>
              <span class="status-note" data-calculate-status="true" aria-live="polite"></span>
            </div>
          </form>
          <section class="alert-card" data-calculate-error-card="true" hidden>
            <h2>Calculation error</h2>
            <p data-calculate-error-summary="true">
              Request could not be completed.
            </p>
            <ul data-calculate-error-list="true" hidden></ul>
          </section>
          <section class="form-card results-panel" data-calculate-results="true" hidden>
            <h2>Latest Calculation Result</h2>
            <p class="hint">
              Returned payload from the local calculate API.
            </p>
            <pre data-calculate-results-json="true"></pre>
          </section>
          <p class="hint">Calculate inputs are saved automatically in this browser.</p>
        """,
    },
}


class _UiServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, _UiRequestHandler)
        self._active_requests = 0
        self._drain_condition = threading.Condition()

    def note_request_started(self) -> None:
        with self._drain_condition:
            self._active_requests += 1

    def note_request_finished(self) -> None:
        with self._drain_condition:
            self._active_requests -= 1
            if self._active_requests <= 0:
                self._drain_condition.notify_all()

    def wait_for_in_flight_requests(self, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        with self._drain_condition:
            while self._active_requests > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._drain_condition.wait(timeout=remaining)

    def server_bind(self) -> None:
        # Avoid HTTPServer reverse DNS (`socket.getfqdn`) stalls on localhost.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        host_name = host if isinstance(host, str) else bytes(host).decode("utf-8")
        self.server_name = host_name
        self.server_port = int(port)


class _UiRequestHandler(BaseHTTPRequestHandler):
    server: _UiServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        _ = (format, args)

    def handle(self) -> None:
        self.server.note_request_started()
        try:
            super().handle()
        finally:
            self.server.note_request_finished()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/calculate"):
            self._write_html(_render_app_shell("calculate"))
            return
        if self.path == "/settings":
            self._write_html(_render_app_shell("settings"))
            return
        if self.path == "/api/v1/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": {"code": "not_found", "message": "Not found"}},
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/v1/calculate":
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "not_found", "message": "Not found"}},
            )
            return

        request_id = str(uuid4())
        try:
            payload = self._read_json_payload()
            request = parse_contract(MealPlanRequest, payload)
            service = MealPlanCalculationService()
            response = service.calculate(request)
        except ValidationError as error:
            self._write_api_error(
                status=HTTPStatus.BAD_REQUEST,
                code="validation_error",
                message="Request validation failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except DomainRuleError as error:
            self._write_api_error(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="domain_rule_error",
                message="Meal-plan domain rule failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
            )
            return

        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _read_json_payload(self) -> object:
        content_length_value = self.headers.get("Content-Length", "0")
        try:
            content_length = int(content_length_value)
        except ValueError as error:
            raise ValidationError("body: invalid Content-Length header") from error
        if content_length <= 0:
            raise ValidationError("body: request JSON body is required")

        raw_body = self.rfile.read(content_length)
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("body: invalid JSON payload") from error

        if not isinstance(parsed, Mapping):
            raise ValidationError("body: expected JSON object")
        return parsed

    def _write_api_error(
        self,
        *,
        status: HTTPStatus,
        code: str,
        message: str,
        request_id: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        error_payload: dict[str, object] = {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
        if details:
            error_payload["details"] = details
        self._write_json(status, {"error": error_payload})

    def _write_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _render_app_shell(active_page: str) -> str:
    content = _PAGE_CONTENT[active_page]
    return _APP_SHELL_TEMPLATE.substitute(
        section_label=content["section_label"],
        title=content["title"],
        description=content["description"],
        content_html=content["content_html"],
        settings_current="page" if active_page == "settings" else "false",
        calculate_current="page" if active_page == "calculate" else "false",
    )


def _error_detail_from_exception(error: Exception) -> dict[str, str]:
    message = str(error).strip()
    if ": " not in message:
        return {"message": message or "Invalid request."}
    field, detail = message.split(": ", maxsplit=1)
    if not field:
        return {"message": detail or "Invalid request."}
    return {"field": field, "message": detail or "Invalid request."}


def run_ui_server() -> None:
    """Start UI mode server and block until SIGINT/SIGTERM shutdown."""
    server = _bind_ui_server()
    host, port = server.server_address[:2]
    host_name = host if isinstance(host, str) else bytes(host).decode("utf-8")
    port_number = int(port)

    print(f"UI available at http://{host_name}:{port_number}/calculate", flush=True)
    print(f"Health endpoint: http://{host_name}:{port_number}/api/v1/health", flush=True)

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: object) -> None:
        _ = (signum, frame)
        stop_event.set()

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    serve_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1})
    serve_thread.start()

    try:
        stop_event.wait()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        server.shutdown()
        server.wait_for_in_flight_requests(SHUTDOWN_DRAIN_SECONDS)
        server.server_close()
        serve_thread.join(timeout=SHUTDOWN_DRAIN_SECONDS)


def _bind_ui_server() -> _UiServer:
    port_start, port_end = _resolve_port_window()
    for port in range(port_start, port_end + 1):
        try:
            return _UiServer((UI_HOST, port))
        except OSError:
            continue
    raise RuntimeError(
        f"UI startup failed: no free port in range {port_start}..{port_end} on {UI_HOST}"
    )


def _resolve_port_window() -> tuple[int, int]:
    start = int(os.environ.get(UI_PORT_START_ENV, str(UI_PORT_START)))
    end = int(os.environ.get(UI_PORT_END_ENV, str(UI_PORT_END)))
    if start > end:
        raise RuntimeError(f"UI startup failed: invalid port window {start}..{end}")
    return start, end
