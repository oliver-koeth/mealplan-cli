"""Local UI mode HTTP server lifecycle and routing."""

from __future__ import annotations

import json
import os
import signal
import socketserver
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UI_HOST = "127.0.0.1"
UI_PORT_START = 8765
UI_PORT_END = 8775
SHUTDOWN_DRAIN_SECONDS = 5.0
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"

_APP_SHELL_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mealplan UI</title>
    <style>
      :root {
        color-scheme: light dark;
        --bg: #f4f6f8;
        --card: #ffffff;
        --text: #1e293b;
        --muted: #475569;
        --border: #cbd5e1;
      }

      @media (prefers-color-scheme: dark) {
        :root {
          --bg: #0b1220;
          --card: #111827;
          --text: #e2e8f0;
          --muted: #94a3b8;
          --border: #334155;
        }
      }

      body {
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
        background:
          radial-gradient(circle at top, rgba(56, 189, 248, 0.12), transparent 55%),
          var(--bg);
        color: var(--text);
      }

      main {
        max-width: 720px;
        margin: 2rem auto;
        padding: 0 1rem;
      }

      .card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1rem;
      }

      h1 {
        margin: 0;
        font-size: 1.35rem;
      }

      p {
        margin-bottom: 0;
        color: var(--muted);
      }
    </style>
  </head>
  <body>
    <main>
      <section class="card">
        <h1>Mealplan Calculate</h1>
        <p>
          Local UI shell is running. Settings and calculate flow are enabled in upcoming stories.
        </p>
      </section>
    </main>
  </body>
</html>
"""


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
            self._write_html(_APP_SHELL_HTML)
            return
        if self.path == "/api/v1/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

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
