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
        const form = document.querySelector('[data-settings-form="true"]');
        if (!form) {
          return;
        }

        const storageKey = "mealplan.ui.settings.v1";
        const fields = [
          "age",
          "gender",
          "height_cm",
          "weight_kg",
          "vo2max",
          "carb_mode",
        ];

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
          const raw = window.localStorage.getItem(storageKey);
          if (!raw) {
            return;
          }
          try {
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
              return;
            }
            for (const name of fields) {
              const control = form.elements.namedItem(name);
              const value = parsed[name];
              if (control && "value" in control && typeof value === "string") {
                control.value = value;
              }
            }
          } catch {
            // Ignore invalid local storage snapshots.
          }
        };

        const persistValues = () => {
          window.localStorage.setItem(storageKey, JSON.stringify(readValues()));
        };

        restoreValues();
        form.addEventListener("input", persistValues);
        form.addEventListener("change", persistValues);
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
          <p class="section-label">Workflow</p>
          <div class="grid">
            <div class="muted-card">
              <h2>Settings</h2>
              <p>
                Profile and baseline controls are grouped in compact cards and
                restored from local storage.
              </p>
            </div>
            <div class="muted-card">
              <h2>Calculate</h2>
              <p>
                Day-specific inputs and results stay in one workflow with inline
                feedback and deterministic API behavior.
              </p>
            </div>
          </div>
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
