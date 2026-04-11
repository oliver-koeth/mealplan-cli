"""Local UI mode HTTP server lifecycle and routing."""

from __future__ import annotations

import json
import os
import signal
import socketserver
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import (
    AUTH_ERROR_DEFAULTS,
    USERS_ATTACH_TOKEN_ROUTE,
    USERS_EXCHANGE_TOKEN_ROUTE,
    USERS_REGISTER_ROUTE,
    ApiErrorEnvelope,
    FoodLogSearchRequest,
    FoodLogUpsertRequest,
    MealPlanRequest,
    MealPlanResponse,
    UserAttachTokenRequest,
    UserAttachTokenResponse,
    UserExchangeTokenRequest,
    UserExchangeTokenResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.infrastructure import (
    JsonCalendarStore,
    JsonFoodLogStore,
    JsonUsersStore,
    PersistedUser,
    canonicalize_user_email,
    generate_bearer_token,
    hash_bearer_token,
    resolve_user_partitioned_path,
    resolve_users_store_path,
    verify_bearer_token,
)
from mealplan.shared.errors import DomainRuleError, ValidationError

UI_HOST = "127.0.0.1"
UI_PORT_START = 8765
UI_PORT_END = 8775
SHUTDOWN_DRAIN_SECONDS = 5.0
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"
CALENDAR_STORE_PATH_ENV = "MEALPLAN_CALENDAR_STORE_PATH"
FOOD_LOG_STORE_PATH_ENV = "MEALPLAN_FOOD_LOG_STORE_PATH"
TRUSTED_PROXY_CIDRS_ENV = "MEALPLAN_TRUSTED_PROXY_CIDRS"
AUTH_RATE_LIMIT_MAX_REQUESTS = 100
AUTH_RATE_LIMIT_WINDOW_SECONDS = 60.0
AUTH_RATE_LIMIT_COOLDOWN_SECONDS = 60.0
_DATE_KEY_FORMAT = "%Y%m%d"
_APP_SHELL_SCRIPT_ROUTE = "/static/app-shell.js"
_UI_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


@dataclass
class _AuthRateLimitEntry:
    attempts: deque[float] = field(default_factory=deque)
    cooldown_until: float = 0.0


class _AuthRateLimiter:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _AuthRateLimitEntry] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def is_limited(self, *, client_ip: str, endpoint_key: str) -> bool:
        now = time.monotonic()
        window_start = now - AUTH_RATE_LIMIT_WINDOW_SECONDS
        key = (client_ip, endpoint_key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _AuthRateLimitEntry()
                self._entries[key] = entry
            if entry.cooldown_until > now:
                return True

            while entry.attempts and entry.attempts[0] <= window_start:
                entry.attempts.popleft()
            entry.attempts.append(now)
            if len(entry.attempts) > AUTH_RATE_LIMIT_MAX_REQUESTS:
                entry.cooldown_until = now + AUTH_RATE_LIMIT_COOLDOWN_SECONDS
                return True
            if not entry.attempts and entry.cooldown_until <= now:
                self._entries.pop(key, None)
            return False

_APP_SHELL_TEMPLATE = Template("""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mealplan UI</title>
    <style>
      :root {
        color-scheme: light;
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
        --accent: #f59e0b;
        --accent-hover: #fbbf24;
        --accent-soft: rgba(245, 158, 11, 0.16);
        --accent-strong: rgba(245, 158, 11, 0.35);
        --accent-text-on: #0b1730;
      }

      :root[data-theme="dark"] {
        color-scheme: dark;
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
        --accent: #f59e0b;
        --accent-hover: #fbbf24;
        --accent-soft: rgba(245, 158, 11, 0.16);
        --accent-strong: rgba(245, 158, 11, 0.35);
        --accent-text-on: #0b1730;
      }

      :root[data-theme="light"] {
        color-scheme: light;
      }

      * {
        box-sizing: border-box;
      }

      [hidden] {
        display: none !important;
      }

      body {
        margin: 0;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        color: var(--text);
        background:
          linear-gradient(180deg, rgba(148, 163, 184, 0.12), transparent 240px),
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

      .header-left {
        display: flex;
        align-items: center;
        gap: 0.55rem;
      }

      .header-menu {
        position: relative;
      }

      .header-menu > summary {
        list-style: none;
      }

      .header-menu > summary::-webkit-details-marker {
        display: none;
      }

      .menu-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2.1rem;
        min-height: 2.1rem;
        border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        background: color-mix(in srgb, var(--surface) 95%, #1d4ed8 5%);
        color: var(--text);
        font-size: 1.05rem;
        line-height: 1;
        cursor: pointer;
      }

      .header-menu[open] .menu-button {
        border-color: var(--accent-strong);
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent);
      }

      .header-menu-panel {
        position: absolute;
        top: calc(100% + 0.45rem);
        left: 0;
        min-width: 10.5rem;
        border-radius: 12px;
        border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        background: linear-gradient(
          150deg,
          color-mix(in srgb, var(--surface) 94%, #1d4ed8 6%),
          color-mix(in srgb, var(--surface-muted) 96%, #0f172a 4%)
        );
        box-shadow: 0 12px 28px color-mix(in srgb, var(--shadow) 65%, transparent);
        padding: 0.3rem;
        display: grid;
        gap: 0.2rem;
        z-index: 30;
      }

      .menu-link {
        text-decoration: none;
        color: var(--text-muted);
        font-size: 0.88rem;
        padding: 0.35rem 0.52rem;
        border-radius: 8px;
        border: 1px solid transparent;
      }

      .menu-link:hover {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 10%, transparent);
      }

      .menu-link[aria-current="page"] {
        color: var(--accent);
        border-color: var(--accent-strong);
        background: color-mix(in srgb, var(--accent) 10%, transparent);
        font-weight: 600;
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
        transition: color 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
      }

      .nav-link:hover {
        color: var(--accent);
        text-decoration: underline;
        text-underline-offset: 0.18rem;
      }

      .nav-link[aria-current="page"] {
        color: var(--accent);
        border-color: var(--accent-strong);
        background: var(--surface);
        font-weight: 600;
        box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent) inset;
      }

      .shell {
        max-width: 1280px;
        margin: 0 auto;
        padding: 1.2rem 1rem 1.4rem;
      }

      .stack {
        max-width: 1320px;
        margin: 0 auto;
        display: grid;
        gap: 1rem;
      }

      .card {
        border: 1px solid color-mix(in srgb, var(--border) 68%, transparent);
        border-radius: 18px;
        background: linear-gradient(
          145deg,
          color-mix(in srgb, var(--surface) 94%, #1d4ed8 6%),
          color-mix(in srgb, var(--surface) 98%, #0f172a 2%)
        );
        box-shadow: 0 16px 44px color-mix(in srgb, var(--shadow) 65%, transparent);
        padding: 1.05rem;
      }

      .stack > .card:first-child {
        border-top: 1px solid var(--accent-strong);
        background:
          linear-gradient(
            128deg,
            color-mix(in srgb, var(--accent) 14%, transparent) 0%,
            color-mix(in srgb, var(--accent) 6%, transparent) 36%,
            transparent 72%
          ),
          linear-gradient(
            145deg,
            color-mix(in srgb, var(--surface) 94%, #1d4ed8 6%),
            color-mix(in srgb, var(--surface) 98%, #0f172a 2%)
          );
        box-shadow:
          0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent) inset,
          0 10px 28px color-mix(in srgb, var(--accent) 14%, transparent),
          0 14px 40px color-mix(in srgb, var(--shadow) 65%, transparent);
      }

      .section-label {
        margin: 0;
        font-size: 0.72rem;
        letter-spacing: 0.11em;
        text-transform: uppercase;
        color: var(--accent);
      }

      .calculate-section-label {
        margin-bottom: 0.7rem;
      }

      [data-log-entry-form="true"] + .calculate-section-label,
      [data-log-search-form="true"] + .calculate-section-label {
        margin-top: 1.15rem;
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
        border-radius: 14px;
        border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        background: linear-gradient(
          155deg,
          color-mix(in srgb, var(--surface-muted) 96%, #1d4ed8 4%),
          color-mix(in srgb, var(--surface) 96%, #0f172a 4%)
        );
        padding: 0.95rem;
      }

      .form-card h2 {
        margin: 0;
        font-size: 0.9rem;
      }

      [data-calculate-form="true"] .form-card h2 {
        font-size: 1.04rem;
        font-weight: 700;
        color: color-mix(in srgb, var(--text) 96%, #ffffff 4%);
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
      select,
      textarea {
        width: 100%;
        border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--border) 74%, transparent);
        background: color-mix(in srgb, var(--surface) 93%, #0f172a 7%);
        color: var(--text);
        font: inherit;
        padding: 0.5rem 0.65rem;
        transition: border-color 120ms ease, box-shadow 120ms ease;
      }

      input:focus,
      select:focus,
      textarea:focus {
        outline: none;
        border-color: var(--accent);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
      }

      .actions {
        margin-top: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.55rem;
        flex-wrap: wrap;
      }

      .date-controls {
        margin-top: 0.8rem;
        display: flex;
        align-items: flex-end;
        gap: 0.65rem;
        flex-wrap: wrap;
      }

      [data-calculate-form="true"] .date-controls {
        align-items: center;
        width: 100%;
        flex-wrap: nowrap;
      }

      [data-log-entry-form="true"] .date-controls {
        align-items: center;
        width: 100%;
        flex-wrap: nowrap;
      }

      [data-calendar-form="true"] .date-controls {
        align-items: center;
        width: 100%;
        flex-wrap: nowrap;
        gap: 0.55rem;
      }

      .date-controls label {
        min-width: 220px;
      }

      [data-calculate-form="true"] .date-controls label {
        min-width: 260px;
        flex: 0 1 300px;
      }

      [data-calculate-form="true"] .date-controls .date-input-wrap {
        min-width: 0;
        flex: 1 1 auto;
      }

      [data-log-entry-form="true"] .date-controls .date-input-wrap {
        min-width: 0;
        flex: 1 1 auto;
      }

      [data-calendar-form="true"] .date-controls .date-input-wrap {
        min-width: 0;
        flex: 1 1 auto;
      }

      .date-input-wrap {
        min-width: 220px;
        flex: 1 1 280px;
      }

      [data-calendar-date-prev="true"],
      [data-calendar-date-next="true"] {
        flex: 0 0 auto;
        width: 2.6rem;
        min-height: 2.6rem;
        border-radius: 12px;
        padding: 0;
        font-size: 1.35rem;
        line-height: 1;
      }

      .field-grid-single {
        margin-top: 0.65rem;
        display: grid;
        gap: 0.65rem;
        grid-template-columns: 1fr;
      }

      .field-span-2 {
        grid-column: 1 / -1;
      }

      .log-entry-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.65rem;
      }

      .log-entry-view-toggle {
        white-space: nowrap;
      }

      .log-entry-json-block {
        margin-top: 0.65rem;
        display: grid;
        gap: 0.65rem;
      }

      .log-entry-json-block label {
        margin: 0;
      }

      .log-entry-json-control {
        min-height: 16rem;
        resize: vertical;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
          "Liberation Mono", "Courier New", monospace;
      }

      .log-search-controls {
        margin-top: 0.65rem;
        display: flex;
        align-items: stretch;
        gap: 0.65rem;
        flex-wrap: wrap;
      }

      .log-search-controls label {
        margin: 0;
        min-width: 180px;
        flex: 1 1 220px;
        display: grid;
        grid-template-rows: auto auto;
        align-content: start;
      }

      .log-search-controls input,
      .log-search-controls select {
        min-height: 3rem;
      }

      .log-search-date-control {
        display: flex;
        align-items: center;
        gap: 0.45rem;
      }

      .log-search-date-control input {
        min-width: 0;
        flex: 1 1 auto;
      }

      .log-search-clear-date {
        min-height: 3rem;
        padding: 0 0.75rem;
        font-weight: 700;
      }

      .log-search-controls .actions {
        margin: 0;
        display: flex;
        align-items: flex-end;
      }

      .log-results-list {
        margin-top: 0.65rem;
        display: grid;
        gap: 0.55rem;
      }

      .log-result-row {
        border-radius: 12px;
        border: 1px solid color-mix(in srgb, var(--border) 74%, transparent);
        background: color-mix(in srgb, var(--surface) 95%, #1d4ed8 5%);
        padding: 0.65rem;
      }

      .log-result-main {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        flex-wrap: wrap;
      }

      .log-result-caret {
        width: 2rem;
        min-height: 2rem;
        padding: 0;
        font-size: 0.95rem;
      }

      .log-result-name {
        margin: 0;
        font-weight: 600;
        color: var(--text);
        flex: 1 1 220px;
      }

      .log-result-kcal {
        margin: 0;
        color: var(--text-muted);
        font-size: 0.82rem;
      }

      .log-result-actions {
        margin-left: auto;
        display: flex;
        align-items: center;
        gap: 0.45rem;
      }

      .log-result-details {
        margin-top: 0.5rem;
        display: grid;
        gap: 0.35rem;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .log-result-details[hidden] {
        display: none;
      }

      .log-result-details p {
        margin: 0;
        font-size: 0.78rem;
        color: var(--text-muted);
      }

      [data-calculate-form="true"] .form-card {
        border-radius: 18px;
      }

      [data-calculate-form="true"] .field-grid {
        gap: 0.75rem;
      }

      [data-calculate-form="true"] label {
        font-size: 0.9rem;
      }

      [data-calculate-form="true"] input,
      [data-calculate-form="true"] select {
        min-height: 2.8rem;
      }

      [data-calculate-date-prev="true"],
      [data-calculate-date-next="true"] {
        flex: 0 0 auto;
        width: 3rem;
        min-height: 3rem;
        border-radius: 14px;
        padding: 0;
        font-size: 1.45rem;
        line-height: 1;
      }

      [data-calculate-submit="true"] {
        border-radius: 16px;
        padding: 0.7rem 1.2rem;
        font-size: 1.1rem;
        font-weight: 700;
      }

      .primary-button {
        border: 1px solid color-mix(in srgb, var(--accent) 65%, #a16207 35%);
        border-radius: 12px;
        background: linear-gradient(
          150deg,
          color-mix(in srgb, var(--accent-hover) 92%, #ffffff 8%),
          color-mix(in srgb, var(--accent) 94%, #a16207 6%)
        );
        color: var(--accent-text-on);
        padding: 0.52rem 0.86rem;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
        transition: transform 100ms ease, box-shadow 120ms ease, background 120ms ease;
      }

      .primary-button:hover {
        background: linear-gradient(
          150deg,
          color-mix(in srgb, var(--accent-hover) 96%, #ffffff 4%),
          color-mix(in srgb, var(--accent-hover) 90%, #a16207 10%)
        );
      }

      .primary-button:active {
        transform: translateY(1px);
      }

      .primary-button[disabled] {
        cursor: wait;
        opacity: 0.7;
      }

      .secondary-button {
        font-weight: 600;
        border-color: color-mix(in srgb, var(--border) 72%, transparent);
        background: linear-gradient(
          150deg,
          color-mix(in srgb, var(--surface) 92%, #1d4ed8 8%),
          color-mix(in srgb, var(--surface-muted) 93%, #0f172a 7%)
        );
        color: var(--accent);
      }

      .secondary-button:hover {
        border-color: var(--accent-strong);
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent);
      }

      .status-note {
        font-size: 0.78rem;
        color: var(--text-subtle);
      }

      .alert-card {
        border-radius: 12px;
        border: 1px solid rgba(220, 38, 38, 0.45);
        background: linear-gradient(145deg, rgba(127, 29, 29, 0.34), rgba(69, 10, 10, 0.28));
        padding: 0.75rem;
        color: #fecaca;
      }

      .success-callout {
        border-radius: 12px;
        border: 1px solid rgba(22, 163, 74, 0.45);
        background: linear-gradient(145deg, rgba(22, 163, 74, 0.2), rgba(21, 128, 61, 0.18));
        color: #14532d;
        padding: 0.75rem;
        width: 100%;
        margin-top: 0.85rem;
        margin-bottom: 0.35rem;
      }

      .success-callout p {
        margin: 0;
        color: inherit;
        font-size: 0.82rem;
      }

      :root[data-theme="dark"] .success-callout {
        color: #bbf7d0;
      }

      .warning-callout {
        border-radius: 12px;
        border: 1px solid rgba(245, 158, 11, 0.55);
        background: linear-gradient(145deg, rgba(245, 158, 11, 0.22), rgba(217, 119, 6, 0.18));
        color: #78350f;
        padding: 0.75rem;
        width: 100%;
        margin-top: 0.85rem;
        margin-bottom: 0.35rem;
      }

      .warning-callout p {
        margin: 0;
        color: inherit;
        font-size: 0.82rem;
      }

      :root[data-theme="dark"] .warning-callout {
        color: #fcd34d;
      }

      .alert-card h2 {
        margin: 0;
        font-size: 0.86rem;
      }

      .alert-card p,
      .alert-card ul {
        margin: 0.45rem 0 0;
        color: #fecaca;
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

      .results-state[hidden],
      .input-state[hidden] {
        display: none;
      }

      .results-totals {
        margin-top: 0.75rem;
        margin-bottom: 1.1rem;
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-start;
        gap: 0.75rem;
      }

      .results-totals[hidden] {
        display: none;
      }

      .results-total {
        width: 176px;
        border-radius: 14px;
        border: 1px solid rgba(217, 119, 6, 0.45);
        background: linear-gradient(
          145deg,
          rgba(217, 119, 6, 0.24),
          rgba(120, 53, 15, 0.2)
        );
        padding: 0.72rem 0.76rem;
      }

      .results-total strong {
        display: block;
        font-size: 0.78rem;
        color: var(--text-subtle);
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }

      .results-total span {
        display: block;
        margin-top: 0.35rem;
        font-size: 0.96rem;
        font-weight: 600;
        color: var(--text);
      }

      .results-total-values {
        margin-top: 0.45rem;
        display: grid;
        gap: 0.28rem;
      }

      .results-total-values p {
        margin: 0;
        font-size: 0.84rem;
        color: var(--text-muted);
        white-space: nowrap;
      }

      .results-total-line {
        display: flex;
        align-items: baseline;
        gap: 0.35rem;
        flex-wrap: nowrap;
        white-space: nowrap;
      }

      .results-total-line span {
        font-weight: 400;
      }

      .results-total-line-label {
        color: var(--text-muted);
      }

      .results-total-line-unit {
        color: var(--text-muted);
      }

      .calendar-daily-progress {
        margin-top: 0.4rem;
        margin-bottom: 1.15rem;
        width: 100%;
        display: grid;
        gap: 0.55rem;
      }

      .calendar-daily-progress[hidden] {
        display: none;
      }

      .calendar-progress-row {
        display: grid;
        grid-template-columns: 72px 1fr auto;
        align-items: center;
        gap: 0.55rem;
      }

      .calendar-progress-row p {
        margin: 0;
        font-size: 0.82rem;
        color: var(--text-muted);
        white-space: nowrap;
      }

      .calendar-progress-track {
        width: 100%;
        min-width: 0;
        height: 0.58rem;
        border-radius: 999px;
        overflow: hidden;
        border: 1px solid color-mix(in srgb, var(--border) 74%, transparent);
        background: color-mix(in srgb, var(--surface-muted) 80%, #0f172a 20%);
      }

      .calendar-progress-fill {
        height: 100%;
        border-radius: 999px;
      }

      .calendar-progress-fill-planned {
        background: #ffffff;
      }

      .calendar-progress-fill-actual-in-band {
        background: #16a34a;
      }

      .calendar-progress-fill-actual-out-of-band {
        background: #dc2626;
      }

      :root[data-theme="dark"] .calendar-progress-fill-planned {
        background: #f8fafc;
      }

      :root[data-theme="dark"] .calendar-progress-fill-actual-in-band {
        background: #86efac;
      }

      :root[data-theme="dark"] .calendar-progress-fill-actual-out-of-band {
        background: #fca5a5;
      }

      .results-meals {
        margin-top: 0.9rem;
        display: grid;
        gap: 0.8rem;
      }

      .meal-result-card {
        border-radius: 16px;
        border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        background: linear-gradient(
          155deg,
          color-mix(in srgb, var(--surface-muted) 97%, #1d4ed8 3%),
          color-mix(in srgb, var(--surface) 96%, #0f172a 4%)
        );
        padding: 0.95rem;
      }

      .meal-result-head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.55rem;
        flex-wrap: wrap;
      }

      .meal-result-head h3 {
        margin: 0;
        font-size: 0.9rem;
      }

      .meal-result-head span {
        color: var(--text-subtle);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }

      .strategy-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 0.2rem 0.56rem;
        border: 1px solid transparent;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }

      .strategy-badge-low {
        background: rgba(22, 163, 74, 0.16);
        color: #166534;
        border-color: rgba(22, 163, 74, 0.42);
      }

      .strategy-badge-medium {
        background: rgba(250, 204, 21, 0.24);
        color: #854d0e;
        border-color: rgba(202, 138, 4, 0.48);
      }

      .strategy-badge-high {
        background: rgba(220, 38, 38, 0.16);
        color: #991b1b;
        border-color: rgba(220, 38, 38, 0.42);
      }

      :root[data-theme="dark"] .strategy-badge-low {
        color: #86efac;
      }

      :root[data-theme="dark"] .strategy-badge-medium {
        color: #fde68a;
      }

      :root[data-theme="dark"] .strategy-badge-high {
        color: #fca5a5;
      }

      .meal-result-grid {
        margin-top: 0.6rem;
        display: grid;
        gap: 0.65rem;
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }

      .meal-result-grid p {
        margin: 0;
        font-size: 0.8rem;
        color: var(--text-muted);
      }

      .meal-macro-row {
        margin-top: 0.55rem;
        display: grid;
        gap: 0.5rem;
      }

      .meal-macro-label {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        font-size: 0.84rem;
        font-weight: 700;
        color: var(--accent);
      }

      .meal-macro-grid {
        display: grid;
        gap: 0.65rem;
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }

      .meal-macro-grid p {
        margin: 0;
        font-size: 0.8rem;
        color: var(--text-muted);
      }

      .meal-actual-toggle {
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
        padding: 0;
      }

      .meal-actual-toggle:disabled {
        cursor: default;
        opacity: 0.65;
      }

      .actual-value-in-band {
        color: #16a34a;
      }

      .actual-value-out-of-band {
        color: #dc2626;
      }

      :root[data-theme="dark"] .actual-value-in-band {
        color: #86efac;
      }

      :root[data-theme="dark"] .actual-value-out-of-band {
        color: #fca5a5;
      }

      .meal-actual-details {
        margin-top: 0.35rem;
        border-top: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        padding-top: 0.55rem;
        display: grid;
        gap: 0.45rem;
      }

      .meal-actual-details[hidden] {
        display: none;
      }

      .meal-actual-entry {
        border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
        background: color-mix(in srgb, var(--surface) 96%, #1d4ed8 4%);
        padding: 0.55rem 0.6rem;
      }

      .meal-actual-entry p {
        margin: 0;
        font-size: 0.78rem;
        color: var(--text-muted);
      }

      .meal-actual-entry-name {
        font-weight: 600;
        color: var(--text);
      }

      .hint {
        margin: 0.65rem 0 0;
        color: var(--text-subtle);
        font-size: 0.78rem;
      }

      .calendar-section-heading {
        margin: 0;
        font-size: 1.12rem;
      }

      .calendar-section-toggle {
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
        padding: 0;
      }

      .calendar-progress-heading {
        margin-top: 0;
        margin-bottom: 0.2rem;
      }

      .calendar-meals-heading {
        margin-top: 0.75rem;
      }

      .calendar-results-state {
        margin-top: 0.95rem;
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

        .log-search-controls label {
          min-width: 0;
          flex: 1 1 100%;
        }

        .log-result-main {
          align-items: flex-start;
        }

        .log-result-actions {
          margin-left: 0;
        }

        .log-result-details {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .meal-result-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .meal-macro-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .results-totals {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(176px, 1fr));
        }

        [data-calendar-form="true"] .date-controls {
          gap: 0.45rem;
        }

        [data-calendar-date-prev="true"],
        [data-calendar-date-next="true"] {
          width: 2.35rem;
          min-height: 2.35rem;
          font-size: 1.2rem;
        }
      }
    </style>
  </head>
  <body>
    <header class="app-header">
      <div class="header-inner">
        <div class="header-left">
          <details class="header-menu">
            <summary class="menu-button" aria-label="Open menu">☰</summary>
            <nav class="header-menu-panel" aria-label="Secondary">
              <a class="menu-link" href="/set-user" aria-current="$set_user_current">Set User</a>
              <a class="menu-link" href="/settings" aria-current="$settings_current">Settings</a>
              <a class="menu-link" href="/privacy" aria-current="$privacy_current">Privacy</a>
            </nav>
          </details>
          <div class="brand">
            <strong>Mealplan</strong>
            <span>UI</span>
          </div>
        </div>
        <nav aria-label="Primary">
          <a class="nav-link" href="/calculate" aria-current="$calculate_current">Calculate</a>
          <a class="nav-link" href="/calendar" aria-current="$calendar_current">Calendar</a>
          <a class="nav-link" href="/log" aria-current="$log_current">Log</a>
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
    <script data-app-shell-inline="true">
      (() => {
        const settingsStorageKey = "mealplan.ui.settings.v1";
        const calculateStorageKey = "mealplan.ui.calculate.v1";
        const calendarDayPlanExpandedStorageKey = "mealplan.ui.calendar.day_plan_expanded.v1";
        const authStorageKey = "mealplan.ui.auth.v1";
        const protectedShellRoutes = new Set(["/", "/calculate", "/calendar", "/log", "/settings"]);
        const supportedThemes = new Set(["light", "dark"]);

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

        const readAuthState = () => readLocalStorageObject(authStorageKey);

        const readAuthToken = () => {
          const authState = readAuthState();
          return typeof authState.token === "string" ? authState.token.trim() : "";
        };

        const dispatchAuthStateChanged = () => {
          window.dispatchEvent(new Event("mealplan-auth-state-changed"));
        };

        const writeAuthState = (nextState) => {
          if (!nextState || typeof nextState !== "object") {
            return;
          }
          window.localStorage.setItem(authStorageKey, JSON.stringify(nextState));
          dispatchAuthStateChanged();
        };

        const clearAuthState = () => {
          window.localStorage.removeItem(authStorageKey);
          dispatchAuthStateChanged();
        };

        const applyProtectedRouteRedirect = () => {
          const currentPath = window.location.pathname;
          if (!protectedShellRoutes.has(currentPath)) {
            return false;
          }
          if (readAuthToken()) {
            return false;
          }
          window.location.replace("/set-user");
          return true;
        };

        const createAuthorizedHeaders = (headers = {}) => {
          const merged = {...headers};
          const token = readAuthToken();
          if (token) {
            merged.Authorization = "Bearer " + token;
          }
          return merged;
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

        const applyTheme = (themeValue) => {
          const documentElement = document.documentElement;
          const resolvedTheme = supportedThemes.has(themeValue) ? themeValue : "light";
          documentElement.dataset.theme = resolvedTheme;
        };

        const settingsSnapshot = readLocalStorageObject(settingsStorageKey);
        const persistedTheme = (
          typeof settingsSnapshot.ui_theme === "string" ? settingsSnapshot.ui_theme : ""
        );
        applyTheme(persistedTheme);
        if (applyProtectedRouteRedirect()) {
          return;
        }

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

        const formatApiErrorMessage = (errorPayload, fallbackMessage) => {
          const fallback = typeof fallbackMessage === "string" && fallbackMessage
            ? fallbackMessage
            : "Request failed.";
          if (!errorPayload || typeof errorPayload !== "object") {
            return fallback;
          }
          const base = (
            typeof errorPayload.message === "string" && errorPayload.message
              ? errorPayload.message
              : fallback
          );
          const details = Array.isArray(errorPayload.details) ? errorPayload.details : [];
          if (details.length === 0) {
            return base;
          }
          const detailText = details
            .map((detail) => {
              if (!detail || typeof detail !== "object") {
                return "";
              }
              const field = typeof detail.field === "string" ? detail.field : "";
              const message = typeof detail.message === "string" ? detail.message : "";
              if (field && message) {
                return field + ": " + message;
              }
              return message || field;
            })
            .filter((value) => typeof value === "string" && value.length > 0)
            .join("; ");
          if (!detailText) {
            return base;
          }
          return base + " (" + detailText + ")";
        };

        const toIsoDate = (dateValue) => {
          const year = dateValue.getFullYear();
          const month = String(dateValue.getMonth() + 1).padStart(2, "0");
          const day = String(dateValue.getDate()).padStart(2, "0");
          return year + "-" + month + "-" + day;
        };

        const normalizeCalendarDate = (rawValue) => {
          if (typeof rawValue !== "string") {
            return null;
          }
          const trimmed = rawValue.trim();
          const isoMatch = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$$/.exec(trimmed);
          if (!isoMatch) {
            return null;
          }
          const [, year, month, day] = isoMatch;
          return year + month + day;
        };

        const settingsForm = document.querySelector('[data-settings-form="true"]');
        bindLocalStorageForm(settingsForm, settingsStorageKey, [
          "age",
          "gender",
          "height_cm",
          "weight_kg",
          "vo2max",
          "carb_mode",
          "activity_level",
          "training_load_tomorrow",
          "training_before_meal",
          "ui_theme",
          "ui_language",
        ]);
        if (settingsForm) {
          const themeControl = settingsForm.elements.namedItem("ui_theme");
          if (themeControl && "value" in themeControl) {
            applyTheme(themeControl.value);
            settingsForm.addEventListener("change", () => {
              applyTheme(themeControl.value);
            });
          }
        }
        const settingsTokenValueControl = document.querySelector(
          '[data-settings-token-value="true"]'
        );
        const settingsTokenRevealButton = document.querySelector(
          '[data-settings-token-reveal="true"]'
        );
        const settingsTokenStatus = document.querySelector('[data-settings-token-status="true"]');
        if (
          settingsTokenValueControl
          && "value" in settingsTokenValueControl
          && settingsTokenRevealButton
          && settingsTokenStatus
        ) {
          let isTokenRevealed = false;
          const maskToken = (token) => "*".repeat(token.length);
          const renderSettingsToken = () => {
            const token = readAuthToken();
            if (!token) {
              isTokenRevealed = false;
              settingsTokenRevealButton.disabled = true;
              settingsTokenRevealButton.textContent = "Reveal Token";
              settingsTokenValueControl.value = "";
              settingsTokenStatus.textContent = "No bearer token attached in this browser.";
              return;
            }
            settingsTokenRevealButton.disabled = false;
            if (isTokenRevealed) {
              settingsTokenRevealButton.textContent = "Hide Token";
              settingsTokenValueControl.value = token;
              settingsTokenStatus.textContent = "Token is visible.";
              return;
            }
            settingsTokenRevealButton.textContent = "Reveal Token";
            settingsTokenValueControl.value = maskToken(token);
            settingsTokenStatus.textContent = "Token is masked.";
          };
          settingsTokenRevealButton.addEventListener("click", () => {
            isTokenRevealed = !isTokenRevealed;
            renderSettingsToken();
          });
          window.addEventListener("mealplan-auth-state-changed", () => {
            isTokenRevealed = false;
            renderSettingsToken();
          });
          window.addEventListener("storage", (event) => {
            if (event.key === authStorageKey) {
              isTokenRevealed = false;
              renderSettingsToken();
            }
          });
          renderSettingsToken();
        }

        const setUserRegisterForm = document.querySelector('[data-set-user-register-form="true"]');
        const setUserAttachForm = document.querySelector('[data-set-user-attach-form="true"]');
        const calculateForm = document.querySelector('[data-calculate-form="true"]');
        const calendarForm = document.querySelector('[data-calendar-form="true"]');
        const logEntryForm = document.querySelector('[data-log-entry-form="true"]');
        const logSearchForm = document.querySelector('[data-log-search-form="true"]');
        let logEntryBindings = null;

        const shiftIsoDateControl = (dateControl, deltaDays) => {
          if (!dateControl || !("value" in dateControl) || !Number.isFinite(deltaDays)) {
            return;
          }
          const baseIso = dateControl.value || toIsoDate(new Date());
          const parsedBase = new Date(baseIso + "T00:00:00");
          if (Number.isNaN(parsedBase.getTime())) {
            dateControl.value = toIsoDate(new Date());
            return;
          }
          parsedBase.setDate(parsedBase.getDate() + deltaDays);
          dateControl.value = toIsoDate(parsedBase);
        };

        if (setUserRegisterForm && setUserAttachForm) {
          const registerEmailControl = setUserRegisterForm.elements.namedItem("email");
          const registerNameControl = setUserRegisterForm.elements.namedItem("name");
          const registerSubmitButton = setUserRegisterForm.querySelector(
            '[data-set-user-register-submit="true"]'
          );
          const registerStatus = document.querySelector('[data-set-user-register-status="true"]');
          const registerTokenCard = document.querySelector('[data-set-user-register-token="true"]');
          const registerTokenValue = document.querySelector(
            '[data-set-user-register-token-value="true"]'
          );

          const attachEmailControl = setUserAttachForm.elements.namedItem("email");
          const attachTokenControl = setUserAttachForm.elements.namedItem("token");
          const attachSubmitButton = setUserAttachForm.querySelector(
            '[data-set-user-attach-submit="true"]'
          );
          const attachStatus = document.querySelector('[data-set-user-attach-status="true"]');
          const authActions = document.querySelector('[data-set-user-auth-actions="true"]');
          const rotateTokenButton = document.querySelector('[data-set-user-rotate-token="true"]');
          const logoutButton = document.querySelector('[data-set-user-logout="true"]');
          const authActionsStatus = document.querySelector(
            '[data-set-user-auth-actions-status="true"]'
          );

          if (
            registerEmailControl
            && "value" in registerEmailControl
            && registerNameControl
            && "value" in registerNameControl
            && registerSubmitButton
            && registerStatus
            && registerTokenCard
            && registerTokenValue
            && attachEmailControl
            && "value" in attachEmailControl
            && attachTokenControl
            && "value" in attachTokenControl
            && attachSubmitButton
            && attachStatus
            && authActions
            && rotateTokenButton
            && logoutButton
            && authActionsStatus
          ) {
            const setRegisterStatus = (message) => {
              registerStatus.textContent = message;
            };

            const setAttachStatus = (message) => {
              attachStatus.textContent = message;
            };

            const setAuthActionsStatus = (message) => {
              authActionsStatus.textContent = message;
            };

            const hideRegisterToken = () => {
              registerTokenCard.hidden = true;
              registerTokenValue.textContent = "";
            };

            const syncAuthActionsVisibility = () => {
              authActions.hidden = !readAuthToken();
            };

            const resetSetUserState = () => {
              clearAuthState();
              registerEmailControl.value = "";
              registerNameControl.value = "";
              attachEmailControl.value = "";
              attachTokenControl.value = "";
              hideRegisterToken();
              setRegisterStatus("");
              setAttachStatus("");
              syncAuthActionsVisibility();
            };

            hideRegisterToken();
            setRegisterStatus("");
            setAttachStatus("");
            setAuthActionsStatus("");

            const maybePrefillEmail = () => {
              const authState = readAuthState();
              if (!registerEmailControl.value && typeof authState.email === "string") {
                registerEmailControl.value = authState.email;
              }
              if (!attachEmailControl.value && typeof authState.email === "string") {
                attachEmailControl.value = authState.email;
              }
            };
            maybePrefillEmail();
            syncAuthActionsVisibility();

            registerSubmitButton.addEventListener("click", async () => {
              const email = registerEmailControl.value.trim();
              const name = registerNameControl.value.trim();
              hideRegisterToken();
              setAuthActionsStatus("");
              if (!email || !name) {
                setRegisterStatus("Email and name are required.");
                return;
              }
              registerSubmitButton.disabled = true;
              setRegisterStatus("Registering user...");
              try {
                const response = await window.fetch("/api/v1/users/register", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  body: JSON.stringify({email, name}),
                });
                let payload = null;
                try {
                  payload = await response.json();
                } catch {
                  payload = null;
                }
                if (!response.ok) {
                  const errorPayload = payload?.error ?? null;
                  setRegisterStatus(
                    formatApiErrorMessage(errorPayload, "Unable to register user.")
                  );
                  return;
                }
                const token = typeof payload?.token === "string" ? payload.token : "";
                const canonicalEmail = typeof payload?.email === "string" ? payload.email : email;
                const persistedName = typeof payload?.name === "string" ? payload.name : name;
                if (!token) {
                  setRegisterStatus("Registration succeeded but token response was missing.");
                  return;
                }
                writeAuthState({
                  email: canonicalEmail,
                  name: persistedName,
                  token,
                });
                registerTokenValue.textContent = token;
                registerTokenCard.hidden = false;
                attachEmailControl.value = canonicalEmail;
                setRegisterStatus("User registered. Token saved in this browser.");
                syncAuthActionsVisibility();
              } catch (error) {
                const rootCause = (
                  error && typeof error === "object" && "message" in error
                    ? String(error.message)
                    : ""
                );
                setRegisterStatus(
                  rootCause ? ("Unable to reach local auth API. " + rootCause) :
                    "Unable to reach local auth API."
                );
              } finally {
                registerSubmitButton.disabled = false;
              }
            });

            attachSubmitButton.addEventListener("click", async () => {
              const email = attachEmailControl.value.trim();
              const token = attachTokenControl.value.trim();
              setAttachStatus("");
              setAuthActionsStatus("");
              if (!email || !token) {
                setAttachStatus("Email and token are required.");
                return;
              }
              attachSubmitButton.disabled = true;
              setAttachStatus("Validating token...");
              try {
                const response = await window.fetch("/api/v1/users/attach-token", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  body: JSON.stringify({email, token}),
                });
                let payload = null;
                try {
                  payload = await response.json();
                } catch {
                  payload = null;
                }
                if (!response.ok) {
                  const errorPayload = payload?.error ?? null;
                  setAttachStatus(
                    formatApiErrorMessage(errorPayload, "Unable to attach token.")
                  );
                  return;
                }
                const canonicalEmail = typeof payload?.email === "string" ? payload.email : email;
                const name = typeof payload?.name === "string" ? payload.name : "";
                writeAuthState({
                  email: canonicalEmail,
                  name,
                  token,
                });
                registerEmailControl.value = canonicalEmail;
                setAttachStatus("Token attached and saved in this browser.");
                syncAuthActionsVisibility();
              } catch (error) {
                const rootCause = (
                  error && typeof error === "object" && "message" in error
                    ? String(error.message)
                    : ""
                );
                setAttachStatus(
                  rootCause ? ("Unable to reach local auth API. " + rootCause) :
                    "Unable to reach local auth API."
                );
              } finally {
                attachSubmitButton.disabled = false;
              }
            });

            logoutButton.addEventListener("click", () => {
              resetSetUserState();
              setAuthActionsStatus("Logged out. Local bearer token removed.");
            });

            rotateTokenButton.addEventListener("click", async () => {
              const authState = readAuthState();
              const currentToken = (
                typeof authState.token === "string" ? authState.token.trim() : ""
              );
              const email = typeof authState.email === "string" ? authState.email.trim() : "";
              if (!currentToken) {
                setAuthActionsStatus("Attach or register a token before rotating.");
                syncAuthActionsVisibility();
                return;
              }
              rotateTokenButton.disabled = true;
              setAuthActionsStatus("Rotating token...");
              try {
                const response = await window.fetch("/api/v1/users/exchange-token", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  body: JSON.stringify({token: currentToken}),
                });
                let payload = null;
                try {
                  payload = await response.json();
                } catch {
                  payload = null;
                }
                if (!response.ok) {
                  const errorPayload = payload?.error ?? null;
                  setAuthActionsStatus(
                    formatApiErrorMessage(errorPayload, "Unable to rotate token.")
                  );
                  syncAuthActionsVisibility();
                  return;
                }
                const rotatedToken = typeof payload?.token === "string" ? payload.token.trim() : "";
                if (!rotatedToken) {
                  setAuthActionsStatus("Token rotation succeeded but no token was returned.");
                  syncAuthActionsVisibility();
                  return;
                }
                writeAuthState({
                  ...authState,
                  email,
                  token: rotatedToken,
                });
                syncAuthActionsVisibility();
                setAuthActionsStatus("Token rotated and saved in this browser.");
              } catch (error) {
                const rootCause = (
                  error && typeof error === "object" && "message" in error
                    ? String(error.message)
                    : ""
                );
                setAuthActionsStatus(
                  rootCause ? ("Unable to reach local auth API. " + rootCause) :
                    "Unable to reach local auth API."
                );
              } finally {
                rotateTokenButton.disabled = false;
              }
            });
          }
        }

        if (logEntryForm) {
          const logDateControl = logEntryForm.elements.namedItem("date");
          const logUuidControl = logEntryForm.elements.namedItem("uuid");
          const logMealControl = logEntryForm.elements.namedItem("meal");
          const logNameControl = logEntryForm.elements.namedItem("name");
          const logKcalControl = logEntryForm.elements.namedItem("kcal");
          const logCarbsControl = logEntryForm.elements.namedItem("carbs");
          const logFatControl = logEntryForm.elements.namedItem("fat");
          const logProteinControl = logEntryForm.elements.namedItem("protein");
          const logFiberControl = logEntryForm.elements.namedItem("fiber");
          const logEntryViewToggleButton = logEntryForm.querySelector(
            '[data-log-entry-view-toggle="true"]'
          );
          const logEntryToggle = logEntryForm.querySelector('[data-log-entry-toggle="true"]');
          const logEntryBody = logEntryForm.querySelector('[data-log-entry-body="true"]');
          const logEntryFormFields = logEntryForm.querySelector(
            '[data-log-entry-form-fields="true"]'
          );
          const logEntryJsonFields = logEntryForm.querySelector(
            '[data-log-entry-json-fields="true"]'
          );
          const logEntryJsonControl = logEntryForm.querySelector(
            '[data-log-entry-json-input="true"]'
          );
          const logPreviousDayButton = logEntryForm.querySelector('[data-log-date-prev="true"]');
          const logNextDayButton = logEntryForm.querySelector('[data-log-date-next="true"]');
          const logEntrySubmitButton = logEntryForm.querySelector('[data-log-entry-submit="true"]');
          const logEntryClearButton = logEntryForm.querySelector('[data-log-entry-clear="true"]');
          const logEntrySuccessCallout = document.querySelector('[data-log-entry-success="true"]');
          if (
            logDateControl
            && "value" in logDateControl
            && logUuidControl
            && "value" in logUuidControl
            && logMealControl
            && "value" in logMealControl
            && logNameControl
            && "value" in logNameControl
            && logKcalControl
            && "value" in logKcalControl
            && logCarbsControl
            && "value" in logCarbsControl
            && logFatControl
            && "value" in logFatControl
            && logProteinControl
            && "value" in logProteinControl
            && logFiberControl
            && "value" in logFiberControl
            && logEntryViewToggleButton
            && logEntryToggle
            && logEntryBody
            && logEntryFormFields
            && logEntryJsonFields
            && logEntryJsonControl
            && "value" in logEntryJsonControl
            && logEntrySubmitButton
            && logEntryClearButton
            && logEntrySuccessCallout
          ) {
            let isLogEntryExpanded = false;
            let logEntryView = "form";

            const syncLogEntryToggle = () => {
              logEntryBody.hidden = !isLogEntryExpanded;
              logEntryToggle.setAttribute(
                "aria-expanded",
                isLogEntryExpanded ? "true" : "false"
              );
              logEntryToggle.textContent = (
                (isLogEntryExpanded ? "▾ " : "▸ ") + "Entry Form"
              );
            };

            const setLogEntryExpanded = (expanded) => {
              isLogEntryExpanded = Boolean(expanded);
              syncLogEntryToggle();
            };

            const createEmptyLogEntryJson = () => ({
              meal: "",
              name: "",
              kcal: "",
              carbs: "",
              fat: "",
              protein: "",
              fiber: "",
            });

            const setLogEntryJsonValue = (entryJson) => {
              logEntryJsonControl.value = JSON.stringify(entryJson, null, 2);
            };

            const syncLogEntryJsonFromForm = () => {
              setLogEntryJsonValue({
                meal: logMealControl.value,
                name: logNameControl.value,
                kcal: logKcalControl.value,
                carbs: logCarbsControl.value,
                fat: logFatControl.value,
                protein: logProteinControl.value,
                fiber: logFiberControl.value,
              });
            };

            const switchLogEntryView = (nextView) => {
              if (nextView !== "json" && nextView !== "form") {
                return;
              }
              if (nextView === "json") {
                syncLogEntryJsonFromForm();
              }
              logEntryView = nextView;
              logEntryFormFields.hidden = nextView !== "form";
              logEntryJsonFields.hidden = nextView !== "json";
              logEntryClearButton.hidden = nextView !== "json";
              logEntryViewToggleButton.setAttribute(
                "aria-pressed",
                nextView === "json" ? "true" : "false"
              );
            };

            const resetLogEntryForm = () => {
              logEntryForm.reset();
              logUuidControl.value = "";
              logDateControl.value = toIsoDate(new Date());
              setLogEntryJsonValue(createEmptyLogEntryJson());
            };

            const setLogEntrySuccess = (message) => {
              if (!message) {
                logEntrySuccessCallout.hidden = true;
                logEntrySuccessCallout.textContent = "";
                return;
              }
              logEntrySuccessCallout.hidden = false;
              logEntrySuccessCallout.textContent = message;
            };

            const updateLogEntryMode = () => {
              const isEditMode = logUuidControl.value.trim().length > 0;
              logEntrySubmitButton.textContent = isEditMode ? "Save" : "Add";
            };

            const fillLogEntryForm = (entry, mode) => {
              if (!entry || typeof entry !== "object") {
                return;
              }
              setLogEntryExpanded(true);
              switchLogEntryView("form");
              if (mode === "edit") {
                logUuidControl.value = typeof entry.uuid === "string" ? entry.uuid : "";
                const canonical = typeof entry.date === "string" ? entry.date.trim() : "";
                if (/^[0-9]{8}$$/.test(canonical)) {
                  logDateControl.value = (
                    canonical.slice(0, 4)
                    + "-"
                    + canonical.slice(4, 6)
                    + "-"
                    + canonical.slice(6, 8)
                  );
                }
              } else {
                logUuidControl.value = "";
                logDateControl.value = toIsoDate(new Date());
              }
              logMealControl.value = typeof entry.meal === "string" ? entry.meal : "";
              logNameControl.value = typeof entry.name === "string" ? entry.name : "";
              logKcalControl.value = Number.isFinite(Number(entry.kcal))
                ? String(Number(entry.kcal))
                : "";
              logCarbsControl.value = Number.isFinite(Number(entry.carbs))
                ? String(Number(entry.carbs))
                : "";
              logFatControl.value = Number.isFinite(Number(entry.fat))
                ? String(Number(entry.fat))
                : "";
              logProteinControl.value = Number.isFinite(Number(entry.protein))
                ? String(Number(entry.protein))
                : "";
              logFiberControl.value = Number.isFinite(Number(entry.fiber))
                ? String(Number(entry.fiber))
                : "";
              updateLogEntryMode();
              syncLogEntryJsonFromForm();
              setLogEntrySuccess("");
            };

            const createLogEntryPayload = () => {
              const canonicalDate = normalizeCalendarDate(logDateControl.value);
              let mealValue = logMealControl.value;
              let nameValue = logNameControl.value.trim();
              let kcal = parseNumberOrNull(logKcalControl.value);
              let carbs = parseNumberOrNull(logCarbsControl.value);
              let fat = parseNumberOrNull(logFatControl.value);
              let protein = parseNumberOrNull(logProteinControl.value);
              let fiber = parseNumberOrNull(logFiberControl.value);
              if (logEntryView === "json") {
                let parsedEntry = null;
                try {
                  parsedEntry = JSON.parse(logEntryJsonControl.value);
                } catch {
                  return null;
                }
                if (!parsedEntry || typeof parsedEntry !== "object" || Array.isArray(parsedEntry)) {
                  return null;
                }
                mealValue = typeof parsedEntry.meal === "string" ? parsedEntry.meal : "";
                nameValue = typeof parsedEntry.name === "string" ? parsedEntry.name.trim() : "";
                kcal = parseNumberOrNull(String(parsedEntry.kcal ?? ""));
                carbs = parseNumberOrNull(String(parsedEntry.carbs ?? ""));
                fat = parseNumberOrNull(String(parsedEntry.fat ?? ""));
                protein = parseNumberOrNull(String(parsedEntry.protein ?? ""));
                fiber = parseNumberOrNull(String(parsedEntry.fiber ?? ""));
              }
              if (
                !canonicalDate
                || !mealValue
                || !nameValue
                || kcal === null
                || carbs === null
                || fat === null
                || protein === null
                || fiber === null
              ) {
                return null;
              }
              return {
                date: canonicalDate,
                meal: mealValue,
                name: nameValue,
                kcal,
                carbs,
                fat,
                protein,
                fiber,
              };
            };

            if (!logDateControl.value) {
              logDateControl.value = toIsoDate(new Date());
            }
            if (!logEntryJsonControl.value.trim()) {
              setLogEntryJsonValue(createEmptyLogEntryJson());
            }
            setLogEntryExpanded(false);
            switchLogEntryView("form");
            updateLogEntryMode();
            setLogEntrySuccess("");
            if (logPreviousDayButton) {
              logPreviousDayButton.addEventListener("click", () => {
                shiftIsoDateControl(logDateControl, -1);
                setLogEntrySuccess("");
              });
            }
            if (logNextDayButton) {
              logNextDayButton.addEventListener("click", () => {
                shiftIsoDateControl(logDateControl, 1);
                setLogEntrySuccess("");
              });
            }

            logUuidControl.addEventListener("input", () => {
              updateLogEntryMode();
              setLogEntrySuccess("");
            });
            logEntryViewToggleButton.addEventListener("click", () => {
              switchLogEntryView(logEntryView === "form" ? "json" : "form");
              setLogEntrySuccess("");
            });
            logEntryToggle.addEventListener("click", () => {
              setLogEntryExpanded(!isLogEntryExpanded);
            });
            logEntryForm.addEventListener("input", () => {
              setLogEntrySuccess("");
            });

            logEntryBindings = {
              applyEditEntry: (entry) => {
                fillLogEntryForm(entry, "edit");
              },
              applyAddEntry: (entry) => {
                fillLogEntryForm(entry, "add");
              },
            };

            logEntrySubmitButton.addEventListener("click", async () => {
              const payload = createLogEntryPayload();
              if (!payload) {
                setLogEntrySuccess("");
                return;
              }
              const uuid = logUuidControl.value.trim();
              const isEditMode = uuid.length > 0;
              logEntrySubmitButton.disabled = true;
              try {
                const endpoint = isEditMode ? ("/api/v1/log/" + uuid) : "/api/v1/log";
                const method = isEditMode ? "PUT" : "POST";
                const response = await window.fetch(endpoint, {
                  method,
                  headers: createAuthorizedHeaders({"Content-Type": "application/json"}),
                  body: JSON.stringify(payload),
                });
                if (!response.ok) {
                  setLogEntrySuccess("");
                  return;
                }
                resetLogEntryForm();
                updateLogEntryMode();
                setLogEntrySuccess(isEditMode ? "Entry saved." : "Entry added.");
              } catch {
                setLogEntrySuccess("");
              } finally {
                logEntrySubmitButton.disabled = false;
              }
            });

            logEntryClearButton.addEventListener("click", () => {
              if (logEntryView !== "json") {
                return;
              }
              logEntryJsonControl.value = "";
              setLogEntrySuccess("");
            });
          }
        }

        if (logSearchForm) {
          const logSearchDateControl = logSearchForm.elements.namedItem("date");
          const logSearchNameControl = logSearchForm.elements.namedItem("name");
          const logSearchMealControl = logSearchForm.elements.namedItem("meal");
          const logSearchSubmitButton = logSearchForm.querySelector(
            '[data-log-search-submit="true"]'
          );
          const logSearchClearDateButton = logSearchForm.querySelector(
            '[data-log-search-clear-date="true"]'
          );
          const logResultsStatus = document.querySelector('[data-log-results-status="true"]');
          const logResultsErrorCard = document.querySelector(
            '[data-log-results-error-card="true"]'
          );
          const logResultsErrorSummary = document.querySelector(
            '[data-log-results-error-summary="true"]'
          );
          const logResultsList = document.querySelector('[data-log-results-list="true"]');
          if (
            logSearchDateControl
            && "value" in logSearchDateControl
            && logSearchNameControl
            && "value" in logSearchNameControl
            && logSearchMealControl
            && "value" in logSearchMealControl
            && logSearchSubmitButton
            && logSearchClearDateButton
            && logResultsStatus
            && logResultsErrorCard
            && logResultsErrorSummary
            && logResultsList
          ) {
            const formatNumber = (value) => {
              const parsed = Number(value);
              if (!Number.isFinite(parsed)) {
                return "-";
              }
              return parsed.toFixed(2);
            };

            const setLogResultsStatus = (message) => {
              logResultsStatus.textContent = message;
            };

            const setLogResultsError = (message) => {
              const text = typeof message === "string" ? message.trim() : "";
              if (!text) {
                logResultsErrorSummary.textContent = "";
                logResultsErrorCard.hidden = true;
                return;
              }
              logResultsErrorSummary.textContent = text;
              logResultsErrorCard.hidden = false;
            };

            const clearLogResultsList = () => {
              logResultsList.innerHTML = "";
            };

            const renderLogSearchResults = (entries) => {
              clearLogResultsList();
              if (!Array.isArray(entries) || entries.length === 0) {
                setLogResultsStatus("No matching entries.");
                return;
              }
              setLogResultsStatus("Showing " + String(entries.length) + " result(s).");
              for (const entry of entries) {
                const row = document.createElement("article");
                row.className = "log-result-row";
                row.setAttribute("data-log-result-row", "true");

                const main = document.createElement("div");
                main.className = "log-result-main";

                const caret = document.createElement("button");
                caret.className = "primary-button secondary-button log-result-caret";
                caret.type = "button";
                caret.textContent = ">";
                caret.setAttribute("data-log-result-caret", "true");
                caret.setAttribute("aria-expanded", "false");

                const name = document.createElement("p");
                name.className = "log-result-name";
                name.textContent = typeof entry?.name === "string" ? entry.name : "Entry";

                const kcal = document.createElement("p");
                kcal.className = "log-result-kcal";
                kcal.textContent = formatNumber(entry?.kcal) + " kcal";

                const actions = document.createElement("div");
                actions.className = "log-result-actions";

                const addButton = document.createElement("button");
                addButton.className = "primary-button secondary-button";
                addButton.type = "button";
                addButton.textContent = "Add";
                addButton.setAttribute("data-log-result-add", "true");

                const editButton = document.createElement("button");
                editButton.className = "primary-button secondary-button";
                editButton.type = "button";
                editButton.textContent = "Edit";
                editButton.setAttribute("data-log-result-edit", "true");

                actions.appendChild(addButton);
                actions.appendChild(editButton);

                main.appendChild(caret);
                main.appendChild(name);
                main.appendChild(kcal);
                main.appendChild(actions);

                const details = document.createElement("section");
                details.className = "log-result-details";
                details.hidden = true;
                details.setAttribute("data-log-result-details", "true");
                details.innerHTML = (
                  "<p>Meal: " + (typeof entry?.meal === "string" ? entry.meal : "-") + "</p>"
                  + "<p>Date: " + (typeof entry?.date === "string" ? entry.date : "-") + "</p>"
                  + "<p>UUID: " + (typeof entry?.uuid === "string" ? entry.uuid : "-") + "</p>"
                  + "<p>Carbs: " + formatNumber(entry?.carbs) + " g</p>"
                  + "<p>Fat: " + formatNumber(entry?.fat) + " g</p>"
                  + "<p>Protein: " + formatNumber(entry?.protein) + " g</p>"
                  + "<p>Fiber: " + formatNumber(entry?.fiber) + " g</p>"
                );

                caret.addEventListener("click", () => {
                  const expanded = details.hidden;
                  details.hidden = !expanded;
                  caret.textContent = expanded ? "v" : ">";
                  caret.setAttribute("aria-expanded", expanded ? "true" : "false");
                });
                editButton.addEventListener("click", () => {
                  if (!logEntryBindings) {
                    return;
                  }
                  logEntryBindings.applyEditEntry(entry);
                });
                addButton.addEventListener("click", () => {
                  if (!logEntryBindings) {
                    return;
                  }
                  logEntryBindings.applyAddEntry(entry);
                });

                row.appendChild(main);
                row.appendChild(details);
                logResultsList.appendChild(row);
              }
            };

            const createSearchQuery = () => {
              const query = new URLSearchParams();
              const canonicalDate = normalizeCalendarDate(logSearchDateControl.value);
              const trimmedName = logSearchNameControl.value.trim();
              const meal = logSearchMealControl.value.trim();
              if (canonicalDate) {
                query.set("date", canonicalDate);
              }
              if (trimmedName) {
                query.set("name", trimmedName);
              }
              if (meal) {
                query.set("meal", meal);
              }
              return query.toString();
            };

            const runLogSearch = async () => {
              setLogResultsStatus("Searching...");
              setLogResultsError("");
              clearLogResultsList();
              logSearchSubmitButton.disabled = true;
              try {
                const query = createSearchQuery();
                const endpoint = query ? ("/api/v1/log/search?" + query) : "/api/v1/log/search";
                const response = await window.fetch(endpoint, {
                  method: "GET",
                  headers: createAuthorizedHeaders(),
                });
                if (!response.ok) {
                  let errorPayload = null;
                  try {
                    const parsed = await response.json();
                    errorPayload = parsed?.error ?? null;
                  } catch {
                    errorPayload = null;
                  }
                  setLogResultsStatus("Search failed.");
                  setLogResultsError(
                    formatApiErrorMessage(errorPayload, "Search failed.")
                  );
                  return;
                }
                const payload = await response.json();
                renderLogSearchResults(payload);
              } catch (error) {
                setLogResultsStatus("Search failed.");
                const rootCause = (
                  error && typeof error === "object" && "message" in error
                    ? String(error.message)
                    : ""
                );
                setLogResultsError(
                  rootCause
                    ? "Unable to reach local log search API. " + rootCause
                    : "Unable to reach local log search API."
                );
              } finally {
                logSearchSubmitButton.disabled = false;
              }
            };

            const activateLogSearchDateFilter = () => {
              if (!logSearchDateControl.value) {
                logSearchDateControl.value = toIsoDate(new Date());
              }
            };
            logSearchDateControl.value = "";
            setLogResultsStatus("No results loaded.");
            logSearchSubmitButton.addEventListener("click", () => {
              void runLogSearch();
            });
            logSearchForm.addEventListener("submit", (event) => {
              event.preventDefault();
              void runLogSearch();
            });
            logSearchDateControl.addEventListener("focus", () => {
              activateLogSearchDateFilter();
            });
            logSearchDateControl.addEventListener("click", () => {
              activateLogSearchDateFilter();
            });
            logSearchClearDateButton.addEventListener("click", () => {
              logSearchDateControl.value = "";
              setLogResultsStatus("Date filter cleared.");
              setLogResultsError("");
            });
          }
        }

        if (calendarForm) {
          const calendarDateControl = calendarForm.elements.namedItem("calendar_date");
          const calendarPreviousDayButton = calendarForm.querySelector(
            '[data-calendar-date-prev="true"]'
          );
          const calendarNextDayButton = calendarForm.querySelector(
            '[data-calendar-date-next="true"]'
          );
          const calendarStatusNote = document.querySelector('[data-calendar-status="true"]');
          const calendarErrorCard = document.querySelector('[data-calendar-error-card="true"]');
          const calendarErrorSummary = document.querySelector(
            '[data-calendar-error-summary="true"]'
          );
          const calendarMissingCard = document.querySelector('[data-calendar-missing-card="true"]');
          const calendarResultsState = document.querySelector(
            '[data-calendar-results-state="true"]'
          );
          const calendarResultsPanel = document.querySelector('[data-calendar-results="true"]');
          const calendarTotalsGrid = document.querySelector(
            '[data-calendar-results-totals="true"]'
          );
          const calendarDailyProgress = document.querySelector(
            '[data-calendar-daily-progress="true"]'
          );
          const calendarMealsGrid = document.querySelector('[data-calendar-results-meals="true"]');
          const calendarDayPlanToggle = document.querySelector(
            '[data-calendar-day-plan-toggle="true"]'
          );
          const calendarDayPlanTotals = document.querySelector(
            '[data-calendar-day-plan-totals="true"]'
          );
          if (
            calendarDateControl
            && "value" in calendarDateControl
            && calendarStatusNote
            && calendarErrorCard
            && calendarErrorSummary
            && calendarMissingCard
            && calendarResultsState
            && calendarResultsPanel
            && calendarTotalsGrid
            && calendarDailyProgress
            && calendarMealsGrid
            && calendarDayPlanToggle
            && calendarDayPlanTotals
          ) {
            if (!calendarDateControl.value) {
              calendarDateControl.value = toIsoDate(new Date());
            }
            const mealOrder = [
              "training",
              "breakfast",
              "morning-snack",
              "lunch",
              "afternoon-snack",
              "dinner",
              "evening-snack",
            ];
            let isCalendarDayPlanExpanded = (
              window.localStorage.getItem(calendarDayPlanExpandedStorageKey) !== "false"
            );
            const formatNumber = (value) => {
              if (!Number.isFinite(value)) {
                return "-";
              }
              return Number(value).toFixed(2);
            };
            const syncCalendarDayPlanToggle = () => {
              calendarDayPlanTotals.hidden = !isCalendarDayPlanExpanded;
              calendarDayPlanToggle.setAttribute(
                "aria-expanded",
                isCalendarDayPlanExpanded ? "true" : "false"
              );
              calendarDayPlanToggle.textContent = (
                (isCalendarDayPlanExpanded ? "▾ " : "▸ ") + "Day Plan"
              );
              window.localStorage.setItem(
                calendarDayPlanExpandedStorageKey,
                isCalendarDayPlanExpanded ? "true" : "false"
              );
            };
            syncCalendarDayPlanToggle();
            const formatWholeNumber = (value) => {
              if (!Number.isFinite(value)) {
                return "-";
              }
              return String(Math.round(value));
            };
            const formatMealName = (value) => {
              if (typeof value !== "string") {
                return "Meal";
              }
              return value
                .split("-")
                .map((part) => part ? part.charAt(0).toUpperCase() + part.slice(1) : "")
                .join(" ");
            };

            const formatStrategyLabel = (value) => {
              if (typeof value !== "string") {
                return "n/a";
              }
              const normalized = value.trim();
              if (!normalized) {
                return "n/a";
              }
              return normalized.toUpperCase();
            };

            const strategyBadgeClass = (value) => {
              const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
              if (normalized === "low") {
                return "strategy-badge strategy-badge-low";
              }
              if (normalized === "medium") {
                return "strategy-badge strategy-badge-medium";
              }
              if (normalized === "high") {
                return "strategy-badge strategy-badge-high";
              }
              return "strategy-badge";
            };

            const parseFiniteNumber = (value) => {
              const parsed = Number(value);
              return Number.isFinite(parsed) ? parsed : 0;
            };

            const actualValueClass = (actualValue, plannedValue) => {
              if (!Number.isFinite(actualValue) || !Number.isFinite(plannedValue)) {
                return "";
              }
              if (plannedValue <= 0) {
                return actualValue > 0 ? "actual-value-out-of-band" : "actual-value-in-band";
              }
              const ratio = actualValue / plannedValue;
              if (ratio < 0.8 || ratio > 1.2) {
                return "actual-value-out-of-band";
              }
              return "actual-value-in-band";
            };

            const appendMacroMetric = (container, label, value, unit, valueClassName) => {
              const metric = document.createElement("p");
              const valueNode = document.createElement("span");
              if (typeof valueClassName === "string" && valueClassName) {
                valueNode.className = valueClassName;
              }
              valueNode.textContent = formatNumber(value);
              metric.append(label + ": ");
              metric.appendChild(valueNode);
              metric.append(" " + unit);
              container.appendChild(metric);
            };

            const appendTotalsLine = (container, label, value, unit, valueClassName) => {
              const line = document.createElement("p");
              line.className = "results-total-line";
              const labelNode = document.createElement("span");
              labelNode.className = "results-total-line-label";
              labelNode.textContent = label + ":";
              if (!Number.isFinite(value)) {
                const dashNode = document.createElement("span");
                dashNode.textContent = "-";
                line.appendChild(labelNode);
                line.appendChild(dashNode);
              } else {
                const valueNode = document.createElement("span");
                if (typeof valueClassName === "string" && valueClassName) {
                  valueNode.className = valueClassName;
                }
                valueNode.textContent = formatWholeNumber(value);
                const unitNode = document.createElement("span");
                unitNode.className = "results-total-line-unit";
                unitNode.textContent = unit;
                line.appendChild(labelNode);
                line.appendChild(valueNode);
                line.appendChild(unitNode);
              }
              container.appendChild(line);
            };

            const renderDailyProgressBars = (plannedKcal, actualKcal) => {
              calendarDailyProgress.innerHTML = "";
              calendarDailyProgress.hidden = false;

              const normalizedPlanned = Number.isFinite(plannedKcal) ? Math.max(plannedKcal, 0) : 0;
              const normalizedActual = Number.isFinite(actualKcal) ? Math.max(actualKcal, 0) : 0;
              const maxValue = Math.max(normalizedPlanned, normalizedActual, 1);

              const rows = [
                {
                  label: "Planned",
                  value: normalizedPlanned,
                  fillClassName: "calendar-progress-fill calendar-progress-fill-planned",
                },
                {
                  label: "Actual",
                  value: normalizedActual,
                  fillClassName: (
                    actualValueClass(normalizedActual, normalizedPlanned) === "actual-value-in-band"
                      ? "calendar-progress-fill calendar-progress-fill-actual-in-band"
                      : "calendar-progress-fill calendar-progress-fill-actual-out-of-band"
                  ),
                },
              ];

              for (const rowData of rows) {
                const row = document.createElement("div");
                row.className = "calendar-progress-row";
                const rowLabel = document.createElement("p");
                rowLabel.textContent = rowData.label;
                const track = document.createElement("div");
                track.className = "calendar-progress-track";
                const fill = document.createElement("div");
                fill.className = rowData.fillClassName;
                fill.style.width = String(Math.min((rowData.value / maxValue) * 100, 100)) + "%";
                track.appendChild(fill);
                const rowValue = document.createElement("p");
                rowValue.textContent = formatWholeNumber(rowData.value) + " kcal";
                row.appendChild(rowLabel);
                row.appendChild(track);
                row.appendChild(rowValue);
                calendarDailyProgress.appendChild(row);
              }
            };

            const aggregateLogsByMeal = (entries) => {
              const summaryByMeal = new Map();
              if (!Array.isArray(entries)) {
                return summaryByMeal;
              }
              for (const entry of entries) {
                const mealName = typeof entry?.meal === "string" ? entry.meal : "";
                if (!mealName) {
                  continue;
                }
                const existing = summaryByMeal.get(mealName) ?? {
                  kcal: 0,
                  carbs: 0,
                  fat: 0,
                  protein: 0,
                  entries: [],
                };
                existing.kcal += parseFiniteNumber(entry?.kcal);
                existing.carbs += parseFiniteNumber(entry?.carbs);
                existing.fat += parseFiniteNumber(entry?.fat);
                existing.protein += parseFiniteNumber(entry?.protein);
                existing.entries.push(entry);
                summaryByMeal.set(mealName, existing);
              }
              return summaryByMeal;
            };

            const setCalendarLoadingState = (inFlight) => {
              if (calendarDateControl) {
                calendarDateControl.disabled = inFlight;
              }
              if (calendarPreviousDayButton) {
                calendarPreviousDayButton.disabled = inFlight;
              }
              if (calendarNextDayButton) {
                calendarNextDayButton.disabled = inFlight;
              }
              calendarStatusNote.textContent = inFlight ? "Loading plan..." : "";
            };

            const hideCalendarFeedback = () => {
              calendarErrorCard.hidden = true;
              calendarMissingCard.hidden = true;
            };

            const hideCalendarResults = () => {
              calendarResultsPanel.hidden = true;
              calendarResultsState.hidden = true;
              calendarDailyProgress.hidden = true;
              calendarDailyProgress.innerHTML = "";
              calendarTotalsGrid.innerHTML = "";
              calendarMealsGrid.innerHTML = "";
            };

            const showCalendarError = (message) => {
              hideCalendarResults();
              calendarMissingCard.hidden = true;
              calendarErrorSummary.textContent = message;
              calendarErrorCard.hidden = false;
            };

            const showCalendarMissing = () => {
              hideCalendarResults();
              calendarErrorCard.hidden = true;
              calendarMissingCard.hidden = false;
            };

            const renderCalendarResults = (payload, logEntries) => {
              const actualDayTotals = {
                kcal: 0,
                carbs: 0,
                fat: 0,
                protein: 0,
                fiber: 0,
              };
              if (Array.isArray(logEntries)) {
                for (const entry of logEntries) {
                  actualDayTotals.kcal += parseFiniteNumber(entry?.kcal);
                  actualDayTotals.carbs += parseFiniteNumber(entry?.carbs);
                  actualDayTotals.fat += parseFiniteNumber(entry?.fat);
                  actualDayTotals.protein += parseFiniteNumber(entry?.protein);
                  actualDayTotals.fiber += parseFiniteNumber(entry?.fiber);
                }
              }

              const totals = [
                {
                  label: "Total kcal",
                  planned: Number(payload?.total_kcal),
                  actual: actualDayTotals.kcal,
                  unit: "kcal",
                },
                {
                  label: "Training kcal",
                  planned: Number(payload?.training_kcal),
                  actual: Number.NaN,
                  unit: "kcal",
                },
                {
                  label: "Carbs",
                  planned: Number(payload?.carbs_g),
                  actual: actualDayTotals.carbs,
                  unit: "g",
                },
                {
                  label: "Fat",
                  planned: Number(payload?.fat_g),
                  actual: actualDayTotals.fat,
                  unit: "g",
                },
                {
                  label: "Protein",
                  planned: Number(payload?.protein_g),
                  actual: actualDayTotals.protein,
                  unit: "g",
                },
                {
                  label: "Fiber",
                  planned: 30,
                  actual: actualDayTotals.fiber,
                  unit: "g",
                },
              ];
              calendarTotalsGrid.innerHTML = "";
              for (const total of totals) {
                const card = document.createElement("article");
                card.className = "results-total";
                const title = document.createElement("strong");
                title.textContent = total.label;
                const values = document.createElement("div");
                values.className = "results-total-values";
                appendTotalsLine(values, "Planned", total.planned, total.unit, "");
                appendTotalsLine(
                  values,
                  "Actual",
                  total.actual,
                  total.unit,
                  actualValueClass(total.actual, total.planned),
                );
                card.appendChild(title);
                card.appendChild(values);
                calendarTotalsGrid.appendChild(card);
              }
              renderDailyProgressBars(Number(payload?.total_kcal), actualDayTotals.kcal);

              const rawMeals = Array.isArray(payload?.meals) ? payload.meals : [];
              const meals = [...rawMeals].sort((left, right) => {
                const leftName = typeof left?.meal === "string" ? left.meal : "";
                const rightName = typeof right?.meal === "string" ? right.meal : "";
                const leftIndex = mealOrder.indexOf(leftName);
                const rightIndex = mealOrder.indexOf(rightName);
                const normalizedLeft = leftIndex === -1 ? mealOrder.length : leftIndex;
                const normalizedRight = rightIndex === -1 ? mealOrder.length : rightIndex;
                return normalizedLeft - normalizedRight;
              });
              const logsByMeal = aggregateLogsByMeal(logEntries);
              calendarMealsGrid.innerHTML = "";
              for (const meal of meals) {
                const card = document.createElement("article");
                card.className = "meal-result-card";
                const strategyLabel = formatStrategyLabel(meal?.carbs_strategy);
                const strategyClassName = strategyBadgeClass(meal?.carbs_strategy);
                const mealName = typeof meal?.meal === "string" ? meal.meal : "";
                const plannedKcal = Number(meal?.kcal);
                const plannedCarbs = Number(meal?.carbs_g);
                const plannedFat = Number(meal?.fat_g);
                const plannedProtein = Number(meal?.protein_g);
                const actual = logsByMeal.get(mealName) ?? {
                  kcal: 0,
                  carbs: 0,
                  fat: 0,
                  protein: 0,
                  entries: [],
                };

                const head = document.createElement("div");
                head.className = "meal-result-head";
                const heading = document.createElement("h3");
                heading.textContent = formatMealName(mealName);
                const badge = document.createElement("span");
                badge.className = strategyClassName;
                badge.textContent = strategyLabel;
                head.appendChild(heading);
                head.appendChild(badge);

                const plannedRow = document.createElement("div");
                plannedRow.className = "meal-macro-row";
                const plannedLabel = document.createElement("span");
                plannedLabel.className = "meal-macro-label";
                plannedLabel.textContent = "Planned:";
                const plannedGrid = document.createElement("div");
                plannedGrid.className = "meal-macro-grid";
                appendMacroMetric(plannedGrid, "Calories", plannedKcal, "kcal", "");
                appendMacroMetric(plannedGrid, "Carbs", plannedCarbs, "g", "");
                appendMacroMetric(plannedGrid, "Fat", plannedFat, "g", "");
                appendMacroMetric(plannedGrid, "Protein", plannedProtein, "g", "");
                plannedRow.appendChild(plannedLabel);
                plannedRow.appendChild(plannedGrid);

                const actualRow = document.createElement("div");
                actualRow.className = "meal-macro-row";
                const actualLabel = document.createElement("span");
                actualLabel.className = "meal-macro-label";
                const actualToggle = document.createElement("button");
                actualToggle.type = "button";
                actualToggle.className = "meal-actual-toggle";
                const actualEntryCount = actual.entries.length;
                actualToggle.textContent = (
                  actualEntryCount > 0 ? "▸ Actuals (" + actualEntryCount + ")" : "Actuals (0)"
                );
                actualToggle.disabled = actualEntryCount === 0;
                actualToggle.setAttribute("aria-expanded", "false");
                const actualLabelSuffix = document.createElement("span");
                actualLabelSuffix.textContent = ":";
                actualLabel.appendChild(actualToggle);
                actualLabel.appendChild(actualLabelSuffix);
                const actualGrid = document.createElement("div");
                actualGrid.className = "meal-macro-grid";
                appendMacroMetric(
                  actualGrid,
                  "Calories",
                  actual.kcal,
                  "kcal",
                  actualValueClass(actual.kcal, plannedKcal),
                );
                appendMacroMetric(
                  actualGrid,
                  "Carbs",
                  actual.carbs,
                  "g",
                  actualValueClass(actual.carbs, plannedCarbs),
                );
                appendMacroMetric(
                  actualGrid,
                  "Fat",
                  actual.fat,
                  "g",
                  actualValueClass(actual.fat, plannedFat),
                );
                appendMacroMetric(
                  actualGrid,
                  "Protein",
                  actual.protein,
                  "g",
                  actualValueClass(actual.protein, plannedProtein),
                );
                actualRow.appendChild(actualLabel);
                actualRow.appendChild(actualGrid);

                const actualDetails = document.createElement("div");
                actualDetails.className = "meal-actual-details";
                actualDetails.hidden = true;
                for (const logEntry of actual.entries) {
                  const detailRow = document.createElement("article");
                  detailRow.className = "meal-actual-entry";
                  const detailName = document.createElement("p");
                  detailName.className = "meal-actual-entry-name";
                  detailName.textContent = (
                    typeof logEntry?.name === "string" ? logEntry.name : "Entry"
                  );
                  const detailMacros = document.createElement("p");
                  detailMacros.textContent = (
                    "Calories: "
                    + formatNumber(Number(logEntry?.kcal))
                    + " kcal | Carbs: "
                    + formatNumber(Number(logEntry?.carbs))
                    + " g | Fat: "
                    + formatNumber(Number(logEntry?.fat))
                    + " g | Protein: "
                    + formatNumber(Number(logEntry?.protein))
                    + " g"
                  );
                  detailRow.appendChild(detailName);
                  detailRow.appendChild(detailMacros);
                  actualDetails.appendChild(detailRow);
                }
                if (actualEntryCount > 0) {
                  actualToggle.addEventListener("click", () => {
                    const nextExpanded = actualDetails.hidden;
                    actualDetails.hidden = !nextExpanded;
                    actualToggle.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
                    actualToggle.textContent = (
                      (nextExpanded ? "▾ " : "▸ ")
                      + "Actuals ("
                      + actualEntryCount
                      + ")"
                    );
                  });
                }

                card.appendChild(head);
                card.appendChild(plannedRow);
                card.appendChild(actualRow);
                card.appendChild(actualDetails);
                calendarMealsGrid.appendChild(card);
              }
              hideCalendarFeedback();
              syncCalendarDayPlanToggle();
              calendarResultsPanel.hidden = false;
              calendarResultsState.hidden = false;
            };

            const shiftCalendarDate = (deltaDays) => {
              if (!Number.isFinite(deltaDays)) {
                return;
              }
              const baseIso = calendarDateControl.value || toIsoDate(new Date());
              const parsedBase = new Date(baseIso + "T00:00:00");
              if (Number.isNaN(parsedBase.getTime())) {
                calendarDateControl.value = toIsoDate(new Date());
                return;
              }
              parsedBase.setDate(parsedBase.getDate() + deltaDays);
              calendarDateControl.value = toIsoDate(parsedBase);
            };

            const loadCalendarPlan = async () => {
              const canonicalDate = normalizeCalendarDate(calendarDateControl.value);
              if (!canonicalDate) {
                showCalendarError("Select a valid date before loading.");
                return;
              }
              hideCalendarFeedback();
              setCalendarLoadingState(true);
              try {
                const response = await window.fetch("/api/v1/calendar/" + canonicalDate, {
                  method: "GET",
                  headers: createAuthorizedHeaders(),
                });
                if (response.status === 404) {
                  showCalendarMissing();
                  return;
                }
                const payload = await response.json();
                if (!response.ok) {
                  showCalendarError(formatApiErrorMessage(
                    payload?.error,
                    "Unable to load plan for selected date."
                  ));
                  return;
                }
                let logEntries = [];
                try {
                  const logsResponse = await window.fetch(
                    "/api/v1/log/search?date=" + canonicalDate,
                    {method: "GET", headers: createAuthorizedHeaders()}
                  );
                  if (logsResponse.ok) {
                    const logsPayload = await logsResponse.json();
                    if (Array.isArray(logsPayload)) {
                      logEntries = logsPayload;
                    }
                  }
                } catch {
                  logEntries = [];
                }
                renderCalendarResults(payload, logEntries);
              } catch {
                showCalendarError("Unable to reach local calendar API.");
              } finally {
                setCalendarLoadingState(false);
              }
            };

            if (calendarPreviousDayButton) {
              calendarPreviousDayButton.addEventListener("click", () => {
                shiftCalendarDate(-1);
                void loadCalendarPlan();
              });
            }
            if (calendarNextDayButton) {
              calendarNextDayButton.addEventListener("click", () => {
                shiftCalendarDate(1);
                void loadCalendarPlan();
              });
            }
            calendarDayPlanToggle.addEventListener("click", () => {
              isCalendarDayPlanExpanded = !isCalendarDayPlanExpanded;
              syncCalendarDayPlanToggle();
            });
            calendarDateControl.addEventListener("change", () => {
              void loadCalendarPlan();
            });
            void loadCalendarPlan();
          }
        }

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

        const applyCalculateDefaultsFromSettings = () => {
          if (!calculateForm) {
            return;
          }
          const persistedCalculate = readLocalStorageObject(calculateStorageKey);
          const persistedSettings = readLocalStorageObject(settingsStorageKey);
          const defaultFieldNames = [
            "activity_level",
            "training_load_tomorrow",
            "training_before_meal",
          ];
          for (const fieldName of defaultFieldNames) {
            const control = calculateForm.elements.namedItem(fieldName);
            if (!control || !("value" in control)) {
              continue;
            }
            const hasDayValue = (
              typeof persistedCalculate[fieldName] === "string"
              && persistedCalculate[fieldName].length > 0
            );
            if (hasDayValue) {
              continue;
            }
            const settingsDefault = persistedSettings[fieldName];
            if (typeof settingsDefault === "string") {
              control.value = settingsDefault;
            }
          }
        };
        applyCalculateDefaultsFromSettings();
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
        const dateControl = calculateForm.elements.namedItem("plan_date");
        const previousDayButton = calculateForm.querySelector('[data-calculate-date-prev="true"]');
        const nextDayButton = calculateForm.querySelector('[data-calculate-date-next="true"]');
        const guidance = document.querySelector('[data-training-before-guidance="true"]');
        const saveStatusNote = document.querySelector('[data-calculate-save-status="true"]');
        const saveErrorCard = document.querySelector('[data-calculate-save-error-card="true"]');
        const saveErrorSummary = document.querySelector(
          '[data-calculate-save-error-summary="true"]'
        );
        if (
          !trainingBeforeControl
          || !("value" in trainingBeforeControl)
          || !dateControl
          || !("value" in dateControl)
        ) {
          return;
        }
        if (!dateControl.value) {
          const tomorrowDate = new Date();
          tomorrowDate.setDate(tomorrowDate.getDate() + 1);
          dateControl.value = toIsoDate(tomorrowDate);
        }

        const calculateButton = calculateForm.querySelector('[data-calculate-submit="true"]');
        const statusNote = document.querySelector('[data-calculate-status="true"]');
        const errorCard = document.querySelector('[data-calculate-error-card="true"]');
        const errorSummary = document.querySelector('[data-calculate-error-summary="true"]');
        const errorList = document.querySelector('[data-calculate-error-list="true"]');
        const inputState = document.querySelector('[data-calculate-input-state="true"]');
        const resultsState = document.querySelector('[data-calculate-results-state="true"]');
        const resultsPanel = document.querySelector('[data-calculate-results="true"]');
        const totalsGrid = document.querySelector('[data-calculate-results-totals="true"]');
        const mealsGrid = document.querySelector('[data-calculate-results-meals="true"]');
        const resultsBackButton = document.querySelector('[data-calculate-results-back="true"]');
        const resultsSaveButton = document.querySelector('[data-calculate-results-save="true"]');
        const scaleDownButton = document.querySelector('[data-calculate-scale-down="true"]');
        const scaleUpButton = document.querySelector('[data-calculate-scale-up="true"]');
        const scaleValue = document.querySelector('[data-calculate-scale-value="true"]');
        const mealOrder = [
          "breakfast",
          "morning-snack",
          "lunch",
          "afternoon-snack",
          "dinner",
          "evening-snack",
        ];
        const scaleStepKcal = 100;
        let requestInFlight = false;
        let baselineResultsPayload = null;
        let displayedKcalOffset = 0;

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
            errorSummary.textContent = formatApiErrorMessage(
              errorPayload,
              "Calculation failed."
            );
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
        };

        const setSubmissionState = (inFlight) => {
          requestInFlight = inFlight;
          if (calculateButton) {
            calculateButton.disabled = inFlight;
            calculateButton.textContent = inFlight ? "Calculating..." : "Calculate";
          }
          if (resultsSaveButton) {
            resultsSaveButton.disabled = inFlight;
          }
          if (previousDayButton) {
            previousDayButton.disabled = inFlight;
          }
          if (nextDayButton) {
            nextDayButton.disabled = inFlight;
          }
          if (dateControl) {
            dateControl.disabled = inFlight;
          }
          if (statusNote) {
            statusNote.textContent = inFlight ? "Submitting request..." : "";
          }
        };

        const setSaveStatus = (message) => {
          if (saveStatusNote) {
            saveStatusNote.textContent = "";
          }
          if (saveErrorCard) {
            saveErrorCard.hidden = true;
          }
          if (saveErrorSummary) {
            saveErrorSummary.textContent = "";
          }
          if (typeof message !== "string" || !message) {
            return;
          }
          if (message.startsWith("Save failed:")) {
            if (saveErrorSummary) {
              saveErrorSummary.textContent = message;
            }
            if (saveErrorCard) {
              saveErrorCard.hidden = false;
            }
            return;
          }
          if (saveStatusNote) {
            saveStatusNote.textContent = message;
          }
        };

        const formatNumber = (value) => {
          if (!Number.isFinite(value)) {
            return "-";
          }
          return Number(value).toFixed(2);
        };

        const formatMealName = (value) => {
          if (typeof value !== "string") {
            return "Meal";
          }
          return value
            .split("-")
            .map((part) => part ? part.charAt(0).toUpperCase() + part.slice(1) : "")
            .join(" ");
        };

        const formatStrategyLabel = (value) => {
          if (typeof value !== "string") {
            return "n/a";
          }
          const normalized = value.trim();
          if (!normalized) {
            return "n/a";
          }
          return normalized.toUpperCase();
        };

        const strategyBadgeClass = (value) => {
          const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
          if (normalized === "low") {
            return "strategy-badge strategy-badge-low";
          }
          if (normalized === "medium") {
            return "strategy-badge strategy-badge-medium";
          }
          if (normalized === "high") {
            return "strategy-badge strategy-badge-high";
          }
          return "strategy-badge";
        };

        const buildScaledResults = (payload) => {
          const baselineTotalKcal = Number(payload?.total_kcal);
          const hasScaleBaseline = Number.isFinite(baselineTotalKcal) && baselineTotalKcal > 0;
          const baselineTDEE = Number(payload?.TDEE);
          const displayedTotalKcal = hasScaleBaseline
            ? Math.max(0, baselineTotalKcal + displayedKcalOffset)
            : baselineTotalKcal;
          const scaleFactor = hasScaleBaseline ? displayedTotalKcal / baselineTotalKcal : 1;
          const scaleNumber = (value) => {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) {
              return Number.NaN;
            }
            return numeric * scaleFactor;
          };
          const scaledMeals = Array.isArray(payload?.meals)
            ? payload.meals.map((meal) => {
                return {
                  meal: meal?.meal,
                  carbs_strategy: meal?.carbs_strategy,
                  kcal: scaleNumber(meal?.kcal),
                  protein_g: scaleNumber(meal?.protein_g),
                  carbs_g: scaleNumber(meal?.carbs_g),
                  fat_g: scaleNumber(meal?.fat_g),
                };
              })
            : [];
          const scaledTrainingKcal = Number.isFinite(baselineTDEE)
            ? displayedTotalKcal - baselineTDEE
            : Number(payload?.training_kcal);

          return {
            TDEE: baselineTDEE,
            training_kcal: scaledTrainingKcal,
            protein_g: scaleNumber(payload?.protein_g),
            carbs_g: scaleNumber(payload?.carbs_g),
            fat_g: scaleNumber(payload?.fat_g),
            total_kcal: displayedTotalKcal,
            baseline_total_kcal: baselineTotalKcal,
            has_scale_baseline: hasScaleBaseline,
            meals: scaledMeals,
          };
        };

        const updateScaleControls = (scaledResults) => {
          if (!scaleValue) {
            return;
          }
          if (!scaledResults.has_scale_baseline) {
            scaleValue.textContent = "Scaling unavailable for this response.";
            if (scaleDownButton) {
              scaleDownButton.disabled = true;
            }
            if (scaleUpButton) {
              scaleUpButton.disabled = true;
            }
            return;
          }

          scaleValue.textContent = (
            "Displayed total: "
            + formatNumber(scaledResults.total_kcal)
            + " kcal (baseline "
            + formatNumber(scaledResults.baseline_total_kcal)
            + " kcal)"
          );
          if (scaleDownButton) {
            const minAllowedTotalKcal = Number.isFinite(scaledResults.TDEE)
              ? Math.max(0, scaledResults.TDEE)
              : 0;
            scaleDownButton.disabled = (
              scaledResults.total_kcal - scaleStepKcal
            ) < minAllowedTotalKcal;
          }
          if (scaleUpButton) {
            scaleUpButton.disabled = false;
          }
        };

        const renderResultsState = () => {
          if (!resultsPanel || !resultsState || !inputState || !totalsGrid || !mealsGrid) {
            return;
          }
          if (!baselineResultsPayload) {
            return;
          }

          const scaledResults = buildScaledResults(baselineResultsPayload);
          updateScaleControls(scaledResults);

          const totals = [
            ["Total kcal", scaledResults.total_kcal, "kcal"],
            ["TDEE", scaledResults.TDEE, "kcal"],
            ["Training kcal", scaledResults.training_kcal, "kcal"],
            ["Carbs", scaledResults.carbs_g, "g"],
            ["Fat", scaledResults.fat_g, "g"],
            ["Protein", scaledResults.protein_g, "g"],
          ];
          totalsGrid.innerHTML = "";
          for (const [label, value, unit] of totals) {
            const card = document.createElement("article");
            card.className = "results-total";
            const title = document.createElement("strong");
            title.textContent = label;
            const valueNode = document.createElement("span");
            valueNode.textContent = formatNumber(Number(value)) + " " + unit;
            card.appendChild(title);
            card.appendChild(valueNode);
            totalsGrid.appendChild(card);
          }

          mealsGrid.innerHTML = "";
          const rawMeals = scaledResults.meals;
          const meals = [...rawMeals].sort((left, right) => {
            const leftName = typeof left?.meal === "string" ? left.meal : "";
            const rightName = typeof right?.meal === "string" ? right.meal : "";
            const leftIndex = mealOrder.indexOf(leftName);
            const rightIndex = mealOrder.indexOf(rightName);
            const normalizedLeft = leftIndex === -1 ? mealOrder.length : leftIndex;
            const normalizedRight = rightIndex === -1 ? mealOrder.length : rightIndex;
            return normalizedLeft - normalizedRight;
          });
          for (const meal of meals) {
            const card = document.createElement("article");
            card.className = "meal-result-card";
            const strategyLabel = formatStrategyLabel(meal?.carbs_strategy);
            const strategyClassName = strategyBadgeClass(meal?.carbs_strategy);
            card.innerHTML = (
              '<div class="meal-result-head">'
              + '<h3>' + formatMealName(meal?.meal) + '</h3>'
              + '<span class="' + strategyClassName + '">' + strategyLabel + '</span>'
              + "</div>"
              + '<div class="meal-result-grid">'
              + "<p>Calories: " + formatNumber(Number(meal?.kcal)) + " kcal</p>"
              + "<p>Carbs: " + formatNumber(Number(meal?.carbs_g)) + " g</p>"
              + "<p>Fat: " + formatNumber(Number(meal?.fat_g)) + " g</p>"
              + "<p>Protein: " + formatNumber(Number(meal?.protein_g)) + " g</p>"
              + "</div>"
            );
            mealsGrid.appendChild(card);
          }

          clearApiFeedback();
          inputState.hidden = true;
          resultsPanel.hidden = false;
          resultsState.hidden = false;
        };

        const clearResultsState = () => {
          baselineResultsPayload = null;
          displayedKcalOffset = 0;
          if (totalsGrid) {
            totalsGrid.innerHTML = "";
          }
          if (mealsGrid) {
            mealsGrid.innerHTML = "";
          }
          if (scaleValue) {
            scaleValue.textContent = "";
          }
          if (scaleDownButton) {
            scaleDownButton.disabled = true;
          }
          if (scaleUpButton) {
            scaleUpButton.disabled = true;
          }
        };

        const adjustDisplayedTotalKcal = (deltaKcal) => {
          if (!baselineResultsPayload) {
            return;
          }
          const baselineTotalKcal = Number(baselineResultsPayload.total_kcal);
          if (!Number.isFinite(baselineTotalKcal) || baselineTotalKcal <= 0) {
            return;
          }
          const nextTotalKcal = baselineTotalKcal + displayedKcalOffset + deltaKcal;
          if (nextTotalKcal < 0) {
            return;
          }
          displayedKcalOffset += deltaKcal;
          renderResultsState();
        };

        const closeResultsState = () => {
          if (!resultsState || !inputState || !resultsPanel) {
            return;
          }
          resultsPanel.hidden = true;
          resultsState.hidden = true;
          inputState.hidden = false;
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
            activity_level: (
              calculateSnapshot.activity_level
              || settingsSnapshot.activity_level
              || ""
            ),
            training_load_tomorrow: (
              calculateSnapshot.training_load_tomorrow
              || settingsSnapshot.training_load_tomorrow
              || ""
            ),
            training_session: {
              training_before_meal: (
                calculateSnapshot.training_before_meal
                || settingsSnapshot.training_before_meal
                || null
              ),
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

        const shiftPlanDate = (deltaDays) => {
          if (!Number.isFinite(deltaDays)) {
            return;
          }
          const baseIso = dateControl.value || toIsoDate(new Date());
          const parsedBase = new Date(baseIso + "T00:00:00");
          if (Number.isNaN(parsedBase.getTime())) {
            dateControl.value = toIsoDate(new Date());
            return;
          }
          parsedBase.setDate(parsedBase.getDate() + deltaDays);
          dateControl.value = toIsoDate(parsedBase);
        };

        const createCalendarSavePayload = () => {
          if (!baselineResultsPayload) {
            return null;
          }
          const scaledResults = buildScaledResults(baselineResultsPayload);
          const invalidFields = [];
          const topLevelNumericFields = [
            ["TDEE", scaledResults.TDEE],
            ["training_kcal", scaledResults.training_kcal],
            ["protein_g", scaledResults.protein_g],
            ["carbs_g", scaledResults.carbs_g],
            ["fat_g", scaledResults.fat_g],
            ["total_kcal", scaledResults.total_kcal],
          ];
          for (const [fieldName, fieldValue] of topLevelNumericFields) {
            if (!Number.isFinite(Number(fieldValue))) {
              invalidFields.push(fieldName);
            }
          }
          const meals = Array.isArray(scaledResults.meals) ? scaledResults.meals : [];
          meals.forEach((meal, index) => {
            const metrics = [
              ["kcal", meal?.kcal],
              ["carbs_g", meal?.carbs_g],
              ["fat_g", meal?.fat_g],
              ["protein_g", meal?.protein_g],
            ];
            for (const [metricName, metricValue] of metrics) {
              if (!Number.isFinite(Number(metricValue))) {
                invalidFields.push("meals." + index + "." + metricName);
              }
            }
          });
          if (invalidFields.length > 0) {
            return {
              error: "Save payload contains invalid numeric values: " + invalidFields.join(", "),
              payload: null,
            };
          }
          return {
            error: null,
            payload: {
              TDEE: scaledResults.TDEE,
              training_kcal: scaledResults.training_kcal,
              protein_g: scaledResults.protein_g,
              carbs_g: scaledResults.carbs_g,
              fat_g: scaledResults.fat_g,
              total_kcal: scaledResults.total_kcal,
              meals,
            },
          };
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
          setSaveStatus("");
          setSubmissionState(true);
          try {
            const response = await window.fetch("/api/v1/calculate", {
              method: "POST",
              headers: createAuthorizedHeaders({"Content-Type": "application/json"}),
              body: JSON.stringify(createRequestPayload()),
            });
            const payload = await response.json();
            if (!response.ok) {
              renderApiError(payload.error ?? {});
              return;
            }
            baselineResultsPayload = payload;
            displayedKcalOffset = 0;
            renderResultsState();
          } catch {
            renderApiError({message: "Unable to reach local calculate API."});
          } finally {
            setSubmissionState(false);
          }
        };

        const saveDisplayedResults = async () => {
          if (!baselineResultsPayload || requestInFlight) {
            return;
          }
          const canonicalDate = normalizeCalendarDate(dateControl.value);
          if (!canonicalDate) {
            setSaveStatus("Save failed: select a valid date.");
            return;
          }
          const savePayload = createCalendarSavePayload();
          if (!savePayload) {
            setSaveStatus("Save failed: no calculated plan to persist.");
            return;
          }
          if (savePayload.error) {
            setSaveStatus("Save failed: " + savePayload.error);
            return;
          }

          setSubmissionState(true);
          setSaveStatus("Saving plan...");
          try {
            const response = await window.fetch("/api/v1/calendar/" + canonicalDate, {
              method: "PUT",
              headers: createAuthorizedHeaders({"Content-Type": "application/json"}),
              body: JSON.stringify(savePayload.payload),
            });
            if (!response.ok) {
              let errorPayload = null;
              try {
                const parsed = await response.json();
                errorPayload = parsed?.error ?? null;
              } catch {
                errorPayload = null;
              }
              setSaveStatus("Save failed: " + formatApiErrorMessage(
                errorPayload,
                "Backend rejected the request."
              ));
              return;
            }
            setSaveStatus("Saved for " + canonicalDate + ".");
            clearResultsState();
            closeResultsState();
          } catch {
            setSaveStatus("Save failed: unable to reach local calendar API.");
          } finally {
            setSubmissionState(false);
          }
        };

        updateTrainingBeforeRequirement();
        calculateForm.addEventListener("input", updateTrainingBeforeRequirement);
        calculateForm.addEventListener("change", updateTrainingBeforeRequirement);
        if (previousDayButton) {
          previousDayButton.addEventListener("click", () => {
            shiftPlanDate(-1);
          });
        }
        if (nextDayButton) {
          nextDayButton.addEventListener("click", () => {
            shiftPlanDate(1);
          });
        }
        calculateForm.addEventListener("submit", (event) => {
          event.preventDefault();
          void submitCalculation();
        });
        if (resultsBackButton) {
          resultsBackButton.addEventListener("click", () => {
            closeResultsState();
          });
        }
        if (resultsSaveButton) {
          resultsSaveButton.addEventListener("click", () => {
            void saveDisplayedResults();
          });
        }
        if (scaleDownButton) {
          scaleDownButton.addEventListener("click", () => {
            adjustDisplayedTotalKcal(-scaleStepKcal);
          });
        }
        if (scaleUpButton) {
          scaleUpButton.addEventListener("click", () => {
            adjustDisplayedTotalKcal(scaleStepKcal);
          });
        }
      })();
    </script>
    <script src="/static/app-shell.js"></script>
  </body>
</html>
""")


_PAGE_CONTENT: dict[str, dict[str, str]] = {
    "set-user": {
        "section_label": "Set User",
        "title": "Register or attach your bearer token",
        "description": (
            "Before using calculate, calendar, and log pages, register a user or attach an "
            "existing token for this browser."
        ),
        "content_html": """
          <p class="section-label">User Setup</p>
          <form class="form-stack" data-set-user-register-form="true">
            <section class="form-card">
              <h2>Register New User</h2>
              <div class="field-grid">
                <label>Email
                  <input name="email" type="email" autocomplete="email" required />
                </label>
                <label>Name
                  <input name="name" type="text" autocomplete="name" required />
                </label>
              </div>
              <div class="actions">
                <button class="primary-button" type="button" data-set-user-register-submit="true">
                  Register
                </button>
                <span class="status-note" data-set-user-register-status="true" aria-live="polite">
                </span>
              </div>
              <section class="warning-callout" data-set-user-register-token="true" hidden>
                <p>
                  Token shown once. Store it safely now:
                  <code data-set-user-register-token-value="true"></code>
                </p>
              </section>
            </section>
          </form>
          <form class="form-stack" data-set-user-attach-form="true">
            <section class="form-card">
              <h2>Attach Existing Token</h2>
              <div class="field-grid">
                <label>Email
                  <input name="email" type="email" autocomplete="email" required />
                </label>
                <label>Bearer Token
                  <input name="token" type="text" autocomplete="off" required />
                </label>
              </div>
              <div class="actions">
                <button class="primary-button" type="button" data-set-user-attach-submit="true">
                  Attach Token
                </button>
                <span class="status-note" data-set-user-attach-status="true" aria-live="polite">
                </span>
              </div>
            </section>
          </form>
          <section class="form-card" data-set-user-auth-actions="true" hidden>
            <h2>Token Session</h2>
            <p>Rotate or clear the token currently stored in this browser.</p>
            <div class="actions">
              <button class="secondary-button" type="button" data-set-user-rotate-token="true">
                Rotate Token
              </button>
              <button class="secondary-button" type="button" data-set-user-logout="true">
                Logout
              </button>
              <span class="status-note" data-set-user-auth-actions-status="true" aria-live="polite">
              </span>
            </div>
          </section>
        """,
    },
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
                <label>Default Activity
                  <select name="activity_level" required>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <label>Default Tomorrow Training Load
                  <select name="training_load_tomorrow" required>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <label>Default Training Before Meal
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
            </section>
            <section class="form-card">
              <h2>UI Settings</h2>
              <div class="field-grid">
                <label>Theme
                  <select name="ui_theme" required>
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </label>
                <label>Language
                  <select name="ui_language" required>
                    <option value="en">English</option>
                  </select>
                </label>
              </div>
            </section>
            <section class="form-card">
              <h2>Bearer Token</h2>
              <p class="hint">Stored in this browser for authenticated API requests.</p>
              <div class="field-grid-single">
                <label>Current Token
                  <input
                    name="settings_bearer_token"
                    type="text"
                    readonly
                    data-settings-token-value="true"
                  />
                </label>
              </div>
              <div class="actions">
                <button
                  class="secondary-button"
                  type="button"
                  data-settings-token-reveal="true"
                >
                  Reveal Token
                </button>
                <span class="status-note" data-settings-token-status="true" aria-live="polite">
                </span>
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
          <p class="section-label calculate-section-label">Day Inputs/Results</p>
          <section class="input-state" data-calculate-input-state="true">
            <form class="form-stack" data-calculate-form="true">
              <section class="form-card">
                <h2>Training Context</h2>
                <div class="date-controls">
                  <button
                    class="primary-button secondary-button"
                    type="button"
                    data-calculate-date-prev="true"
                  >
                    &lt;
                  </button>
                  <div class="date-input-wrap">
                    <input
                      name="plan_date"
                      type="date"
                      aria-label="Date"
                      required
                    />
                  </div>
                  <button
                    class="primary-button secondary-button"
                    type="button"
                    data-calculate-date-next="true"
                  >
                    &gt;
                  </button>
                </div>
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
                </div>
                <div class="field-grid-single">
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
                    <input
                      name="zone_1_minutes"
                      type="number"
                      min="0"
                      step="1"
                      value="0"
                      required
                    />
                  </label>
                  <label>Zone 2 Minutes
                    <input
                      name="zone_2_minutes"
                      type="number"
                      min="0"
                      step="1"
                      value="0"
                      required
                    />
                  </label>
                  <label>Zone 3 Minutes
                    <input
                      name="zone_3_minutes"
                      type="number"
                      min="0"
                      step="1"
                      value="0"
                      required
                    />
                  </label>
                  <label>Zone 4 Minutes
                    <input
                      name="zone_4_minutes"
                      type="number"
                      min="0"
                      step="1"
                      value="0"
                      required
                    />
                  </label>
                  <label class="field-span-2">Zone 5 Minutes
                    <input
                      name="zone_5_minutes"
                      type="number"
                      min="0"
                      step="1"
                      value="0"
                      required
                    />
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
          </section>
          <section class="results-state" data-calculate-results-state="true" hidden>
            <section class="form-card results-panel" data-calculate-results="true" hidden>
              <h2>Calculated Meal Plan</h2>
              <p class="hint">
                Review totals and meal details, then go back to adjust inputs.
              </p>
              <div class="actions">
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-calculate-scale-down="true"
                >
                  -100 kcal
                </button>
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-calculate-scale-up="true"
                >
                  +100 kcal
                </button>
                <span class="status-note" data-calculate-scale-value="true"></span>
              </div>
              <section class="results-totals" data-calculate-results-totals="true"></section>
              <section class="results-meals" data-calculate-results-meals="true"></section>
              <div class="actions">
                <button class="primary-button" type="button" data-calculate-results-back="true">
                  Back to inputs
                </button>
                <button class="primary-button" type="button" data-calculate-results-save="true">
                  Save
                </button>
                <span class="status-note" data-calculate-save-status="true" aria-live="polite">
                </span>
              </div>
              <section class="alert-card" data-calculate-save-error-card="true" hidden>
                <p data-calculate-save-error-summary="true">
                  Save failed.
                </p>
              </section>
            </section>
          </section>
        """,
    },
    "calendar": {
        "section_label": "Calendar",
        "title": "Date-based meal-plan lookup",
        "description": (
            "Load saved plans by date without recalculation. This view is read-only and mirrors "
            "the calculate results structure."
        ),
        "content_html": """
          <p class="section-label calculate-section-label">Calendar Lookup</p>
          <form class="form-stack" data-calendar-form="true">
            <section class="form-card">
              <h2>Lookup Date</h2>
              <div class="date-controls">
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-calendar-date-prev="true"
                >
                  &lt;
                </button>
                <div class="date-input-wrap">
                  <input
                    name="calendar_date"
                    type="date"
                    aria-label="Date"
                    required
                  />
                </div>
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-calendar-date-next="true"
                >
                  &gt;
                </button>
              </div>
              <div class="actions">
                <span class="status-note" data-calendar-status="true" aria-live="polite"></span>
              </div>
            </section>
          </form>
          <section class="alert-card" data-calendar-error-card="true" hidden>
            <h2>Calendar lookup error</h2>
            <p data-calendar-error-summary="true">
              Unable to load plan for selected date.
            </p>
          </section>
          <section class="alert-card" data-calendar-missing-card="true" hidden>
            <h2>No meal plan for selected date</h2>
            <p>
              No meal plan exists, you first need to <a href="/calculate">calculate</a> one.
            </p>
          </section>
          <section
            class="results-state calendar-results-state"
            data-calendar-results-state="true"
            hidden
          >
            <section class="form-stack" data-calendar-results="true" hidden>
              <section class="form-card results-panel">
                <h2 class="calendar-section-heading">
                  <button
                    class="calendar-section-toggle"
                    type="button"
                    data-calendar-day-plan-toggle="true"
                    aria-expanded="true"
                  >
                    ▾ Day Plan
                  </button>
                </h2>
                <section
                  class="results-totals"
                  data-calendar-results-totals="true"
                  data-calendar-day-plan-totals="true"
                >
                </section>
              </section>
              <section class="form-card results-panel">
                <h2 class="calendar-section-heading calendar-progress-heading">Day Progress</h2>
                <section class="calendar-daily-progress" data-calendar-daily-progress="true" hidden>
                </section>
              </section>
              <section class="form-card results-panel">
                <h2 class="calendar-section-heading calendar-meals-heading">Meal Plans</h2>
                <section class="results-meals" data-calendar-results-meals="true"></section>
              </section>
            </section>
          </section>
        """,
    },
    "log": {
        "section_label": "Log",
        "title": "Food log entry and search",
        "description": (
            "Capture food entries and browse saved records from one page. Entry actions, search "
            "filters, and results are organized in a single workflow."
        ),
        "content_html": """
          <p class="section-label calculate-section-label">Log Entry</p>
          <form class="form-stack" data-log-entry-form="true">
            <section class="form-card">
              <div class="log-entry-header">
                <h2>
                  <button
                    class="calendar-section-toggle"
                    type="button"
                    data-log-entry-toggle="true"
                    aria-expanded="false"
                  >
                    ▸ Entry Form
                  </button>
                </h2>
                <button
                  class="primary-button secondary-button log-entry-view-toggle"
                  type="button"
                  data-log-entry-view-toggle="true"
                  aria-pressed="false"
                >
                  JSON View
                </button>
              </div>
              <div data-log-entry-body="true" hidden>
              <div class="date-controls">
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-log-date-prev="true"
                >
                  &lt;
                </button>
                <div class="date-input-wrap">
                  <input
                    name="date"
                    type="date"
                    aria-label="Date"
                    required
                  />
                </div>
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-log-date-next="true"
                >
                  &gt;
                </button>
              </div>
              <div class="field-grid" data-log-entry-form-fields="true">
                <label>UUID
                  <input name="uuid" type="text" readonly />
                </label>
                <label>Meal
                  <select name="meal" required>
                    <option value="training">Training</option>
                    <option value="breakfast">Breakfast</option>
                    <option value="morning-snack">Morning snack</option>
                    <option value="lunch">Lunch</option>
                    <option value="afternoon-snack">Afternoon snack</option>
                    <option value="dinner">Dinner</option>
                    <option value="evening-snack">Evening snack</option>
                  </select>
                </label>
                <label class="field-span-2">Name
                  <input name="name" type="text" required />
                </label>
                <label>Kcal
                  <input name="kcal" type="number" min="0" step="0.1" required />
                </label>
                <label>Carbs
                  <input name="carbs" type="number" min="0" step="0.1" required />
                </label>
                <label>Fat
                  <input name="fat" type="number" min="0" step="0.1" required />
                </label>
                <label>Protein
                  <input name="protein" type="number" min="0" step="0.1" required />
                </label>
                <label class="field-span-2">Fiber
                  <input name="fiber" type="number" min="0" step="0.1" required />
                </label>
              </div>
              <div class="log-entry-json-block" data-log-entry-json-fields="true" hidden>
                <label>Entry JSON
                  <textarea
                    name="entry_json"
                    class="log-entry-json-control"
                    data-log-entry-json-input="true"
                    aria-label="Entry JSON"
                  ></textarea>
                </label>
              </div>
              <div class="actions">
                <button class="primary-button" type="button" data-log-entry-submit="true">
                  Add
                </button>
                <button
                  class="primary-button secondary-button"
                  type="button"
                  data-log-entry-clear="true"
                  hidden
                >
                  Clear
                </button>
              </div>
              <section
                class="success-callout"
                data-log-entry-success="true"
                hidden
                aria-live="polite"
              >
              </section>
              </div>
            </section>
          </form>
          <p class="section-label calculate-section-label">Search Controls</p>
          <form class="form-stack" data-log-search-form="true">
            <section class="form-card">
              <h2>Search</h2>
              <div class="log-search-controls">
                <label>Date
                  <div class="log-search-date-control">
                    <input name="date" type="date" aria-label="Search date" />
                    <button
                      class="primary-button secondary-button log-search-clear-date"
                      type="button"
                      data-log-search-clear-date="true"
                      aria-label="Clear date filter"
                    >
                      X
                    </button>
                  </div>
                </label>
                <label>Name
                  <input name="name" type="text" />
                </label>
                <label>Meal
                  <select name="meal">
                    <option value="">Any meal</option>
                    <option value="training">Training</option>
                    <option value="breakfast">Breakfast</option>
                    <option value="morning-snack">Morning snack</option>
                    <option value="lunch">Lunch</option>
                    <option value="afternoon-snack">Afternoon snack</option>
                    <option value="dinner">Dinner</option>
                    <option value="evening-snack">Evening snack</option>
                  </select>
                </label>
                <div class="actions">
                  <button class="primary-button" type="submit" data-log-search-submit="true">
                    Search
                  </button>
                </div>
              </div>
            </section>
          </form>
          <p class="section-label calculate-section-label">Search Results</p>
          <section class="form-card" data-log-results="true">
            <h2>Results</h2>
            <p class="hint" data-log-results-status="true">No results loaded.</p>
            <section class="alert-card" data-log-results-error-card="true" hidden>
              <p data-log-results-error-summary="true">Search failed.</p>
            </section>
            <section class="log-results-list" data-log-results-list="true"></section>
          </section>
        """,
    },
    "privacy": {
        "section_label": "Privacy",
        "title": "GPT Action Privacy Policy",
        "description": (
            "Privacy information for Mealplan GPT Action and local UI/API data handling."
        ),
        "content_html": """
          <section class="form-card">
            <h2>Scope</h2>
            <p>
              This policy applies to requests sent by GPT Actions to Mealplan API endpoints and
              to local UI/API usage that stores user and nutrition data on the running host.
            </p>
            <p>
              Covered endpoints include nutrition logging (for example `POST /api/v1/log`) and
              user/token lifecycle endpoints under `/api/v1/users/*`.
            </p>
          </section>
          <section class="form-card">
            <h2>Data Processed</h2>
            <p>
              The service processes fields required for user identity and nutrition logging:
              user identity fields (`email`, `name`, token verifier metadata) and meal-log fields
              `date`, `meal`, `name`, `kcal`, `carbs`, `fat`, `protein`, and `fiber`.
            </p>
            <p>
              The service generates and returns a `uuid` for each stored log entry.
            </p>
          </section>
          <section class="form-card">
            <h2>Purpose of Processing</h2>
            <p>
              Data is processed solely to create and maintain nutrition log entries requested by
              the user.
            </p>
          </section>
          <section class="form-card">
            <h2>Storage and Retention</h2>
            <p>
              Users are stored in `~/.mealplan/users.json` (override:
              `MEALPLAN_USERS_STORE_PATH`), food logs in `~/.mealplan/food-log.json`
              (`MEALPLAN_FOOD_LOG_STORE_PATH`), and calendar plans in
              `~/.mealplan/calendar.json` (`MEALPLAN_CALENDAR_STORE_PATH`).
            </p>
            <p>
              Data remains stored until it is updated or deleted by the service operator.
            </p>
          </section>
          <section class="form-card">
            <h2>Data Sharing</h2>
            <p>
              Submitted meal-log data is not sold. Data is shared only with infrastructure
              providers required to host and operate the service.
            </p>
          </section>
          <section class="form-card">
            <h2>Security</h2>
            <p>
              Bearer authentication is required on protected API routes. Register and token-attach
              flows are public endpoints, but protected routes require
              `Authorization: Bearer &lt;token&gt;`.
            </p>
            <p>
              Plaintext bearer tokens are never persisted in users storage; only hashed verifier
              metadata is stored.
            </p>
            <p>
              UI auth state stores the token in browser `localStorage` key
              `mealplan.ui.auth.v1`. Because localStorage is JavaScript-accessible, XSS can expose
              tokens; keep strict CSP and avoid inline third-party scripts.
            </p>
            <p>
              CSP baseline for HTML responses is:
              `default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'`,
              `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`,
              `form-action 'self'`.
            </p>
          </section>
          <section class="form-card">
            <h2>User Rights and Contact</h2>
            <p>
              To request correction or deletion of logged entries, contact the service operator for
              this deployment.
            </p>
          </section>
          <section class="form-card">
            <h2>Policy Updates</h2>
            <p>Last updated: 2026-04-11.</p>
            <p>
              This policy may be updated when the endpoint behavior or data handling changes.
            </p>
          </section>
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
    _AUTH_RATE_LIMITER = _AuthRateLimiter()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        _ = (format, args)

    def handle(self) -> None:
        self.server.note_request_started()
        try:
            super().handle()
        finally:
            self.server.note_request_finished()

    def do_GET(self) -> None:  # noqa: N802
        path = self._request_path()
        if path == _APP_SHELL_SCRIPT_ROUTE:
            self._write_javascript(_app_shell_inline_script())
            return
        if path == "/":
            self._write_html(_render_app_shell("calendar"))
            return
        if path == "/set-user":
            self._write_html(_render_app_shell("set-user"))
            return
        if path == "/calculate":
            self._write_html(_render_app_shell("calculate"))
            return
        if path == "/calendar":
            self._write_html(_render_app_shell("calendar"))
            return
        if path == "/log":
            self._write_html(_render_app_shell("log"))
            return
        if path == "/settings":
            self._write_html(_render_app_shell("settings"))
            return
        if path == "/privacy":
            self._write_html(_render_app_shell("privacy"))
            return
        if path == "/api/v1/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/v1/log/search":
            self._handle_log_search_get()
            return
        calendar_date = _calendar_date_from_path(path)
        if calendar_date is not None:
            self._handle_calendar_get(calendar_date)
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": {"code": "not_found", "message": "Not found"}},
        )

    def do_POST(self) -> None:  # noqa: N802
        path = self._request_path()
        if path == "/api/v1/calculate":
            self._handle_calculate_post()
            return
        if path == "/api/v1/log":
            self._handle_log_post()
            return
        if path == USERS_REGISTER_ROUTE:
            self._handle_users_register_post()
            return
        if path == USERS_ATTACH_TOKEN_ROUTE:
            self._handle_users_attach_token_post()
            return
        if path == USERS_EXCHANGE_TOKEN_ROUTE:
            self._handle_users_exchange_token_post()
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": {"code": "not_found", "message": "Not found"}},
        )

    def do_PUT(self) -> None:  # noqa: N802
        path = self._request_path()
        calendar_date = _calendar_date_from_path(path)
        if calendar_date is not None:
            self._handle_calendar_put(calendar_date)
            return
        log_uuid = _log_uuid_from_path(path)
        if log_uuid is not None:
            self._handle_log_put(log_uuid)
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": {"code": "not_found", "message": "Not found"}},
        )

    def _handle_calculate_post(self) -> None:
        request_id = str(uuid4())
        if (
            self._require_authenticated_user(
                request_id=request_id,
                endpoint_key="/api/v1/calculate",
            )
            is None
        ):
            return
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
        except PydanticValidationError as error:
            self._write_api_error(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="response_validation_error",
                message="Calculation response validation failed.",
                request_id=request_id,
                details=[_error_detail_from_pydantic_validation(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return

        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_log_post(self) -> None:
        request_id = str(uuid4())
        authenticated_user = self._require_authenticated_user(
            request_id=request_id,
            endpoint_key="/api/v1/log",
        )
        if authenticated_user is None:
            return
        store = JsonFoodLogStore(_user_food_log_store_path(user=authenticated_user))
        try:
            payload = self._read_json_payload()
            request = parse_contract(FoodLogUpsertRequest, payload)
            response = store.create(request=request)
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
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_users_register_post(self) -> None:
        request_id = str(uuid4())
        users_store = JsonUsersStore(resolve_users_store_path())
        try:
            payload = self._read_json_payload()
            request = parse_contract(UserRegisterRequest, payload)
            email = canonicalize_user_email(request.email)
            if not email:
                raise ValidationError("email: value is required")
            token = generate_bearer_token()
            created_user = users_store.create_user(
                email=email,
                name=request.name,
                token_verifier=hash_bearer_token(token=token),
            )
            if created_user is None:
                self._write_auth_error(code="user_already_exists", request_id=request_id)
                return
            response = UserRegisterResponse(
                email=created_user.email,
                name=created_user.name,
                token=token,
            )
        except ValidationError as error:
            self._write_api_error(
                status=HTTPStatus.BAD_REQUEST,
                code="validation_error",
                message="Request validation failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_users_attach_token_post(self) -> None:
        request_id = str(uuid4())
        users_store = JsonUsersStore(resolve_users_store_path())
        try:
            payload = self._read_json_payload()
            request = parse_contract(UserAttachTokenRequest, payload)
            email = canonicalize_user_email(request.email)
            if not email:
                raise ValidationError("email: value is required")
            user = self._resolve_user_for_token(token=request.token, users_store=users_store)
            if user is None:
                self._write_auth_error(code="auth_invalid_token", request_id=request_id)
                return
            if user.email != email:
                self._write_auth_error(code="auth_token_email_mismatch", request_id=request_id)
                return
            response = UserAttachTokenResponse(email=user.email, name=user.name)
        except ValidationError as error:
            self._write_api_error(
                status=HTTPStatus.BAD_REQUEST,
                code="validation_error",
                message="Request validation failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_users_exchange_token_post(self) -> None:
        request_id = str(uuid4())
        users_store = JsonUsersStore(resolve_users_store_path())
        try:
            payload = self._read_json_payload()
            request = parse_contract(UserExchangeTokenRequest, payload)
            existing_user = self._resolve_user_for_token(
                token=request.token,
                users_store=users_store,
            )
            if existing_user is None:
                self._write_auth_error(code="auth_invalid_token", request_id=request_id)
                return
            new_token = generate_bearer_token()
            users_store.upsert_user(
                email=existing_user.email,
                name=existing_user.name,
                token_verifier=hash_bearer_token(token=new_token),
            )
            response = UserExchangeTokenResponse(token=new_token)
        except ValidationError as error:
            self._write_api_error(
                status=HTTPStatus.BAD_REQUEST,
                code="validation_error",
                message="Request validation failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_log_put(self, entry_uuid: str) -> None:
        request_id = str(uuid4())
        authenticated_user = self._require_authenticated_user(
            request_id=request_id,
            endpoint_key="/api/v1/log/{uuid}",
        )
        if authenticated_user is None:
            return
        store = JsonFoodLogStore(_user_food_log_store_path(user=authenticated_user))
        try:
            payload = dict(self._read_json_payload())
            payload["uuid"] = entry_uuid
            request = parse_contract(FoodLogUpsertRequest, payload)
            response = store.update(request=request)
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
            if _is_log_not_found_error(error):
                self._write_api_error(
                    status=HTTPStatus.NOT_FOUND,
                    code="log_not_found",
                    message="Log entry not found.",
                    request_id=request_id,
                    details=[_error_detail_from_exception(error)],
                )
                return
            self._write_api_error(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="domain_rule_error",
                message="Meal-plan domain rule failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_log_search_get(self) -> None:
        request_id = str(uuid4())
        authenticated_user = self._require_authenticated_user(
            request_id=request_id,
            endpoint_key="/api/v1/log/search",
        )
        if authenticated_user is None:
            return
        store = JsonFoodLogStore(_user_food_log_store_path(user=authenticated_user))
        try:
            request = parse_contract(
                FoodLogSearchRequest,
                {
                    "date": self._single_query_param("date"),
                    "name": self._single_query_param("name"),
                    "meal": self._single_query_param("meal"),
                },
            )
            response = store.search(request=request)
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
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(
            HTTPStatus.OK,
            [entry.model_dump(mode="json") for entry in response],
        )

    def _handle_calendar_get(self, date_key: str) -> None:
        request_id = str(uuid4())
        authenticated_user = self._require_authenticated_user(
            request_id=request_id,
            endpoint_key="/api/v1/calendar/{date}",
        )
        if authenticated_user is None:
            return
        store = JsonCalendarStore(_user_calendar_store_path(user=authenticated_user))
        try:
            canonical_date = _normalize_calendar_date(date_key)
            response_payload = store.get(date_key=canonical_date)
            response = parse_contract(MealPlanResponse, response_payload)
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
            if _is_calendar_not_found_error(error):
                self._write_api_error(
                    status=HTTPStatus.NOT_FOUND,
                    code="calendar_not_found",
                    message="Meal plan not found for requested date.",
                    request_id=request_id,
                    details=[_error_detail_from_exception(error)],
                )
                return
            self._write_api_error(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="domain_rule_error",
                message="Meal-plan domain rule failed.",
                request_id=request_id,
                details=[_error_detail_from_exception(error)],
            )
            return
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))

    def _handle_calendar_put(self, date_key: str) -> None:
        request_id = str(uuid4())
        authenticated_user = self._require_authenticated_user(
            request_id=request_id,
            endpoint_key="/api/v1/calendar/{date}",
        )
        if authenticated_user is None:
            return
        store = JsonCalendarStore(_user_calendar_store_path(user=authenticated_user))
        try:
            payload = self._read_json_payload()
            response = parse_contract(MealPlanResponse, payload)
            canonical_date = _normalize_calendar_date(date_key)
            store.save(date_key=canonical_date, payload=response.model_dump(mode="json"))
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
        except Exception as error:  # noqa: BLE001
            self._write_api_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
                details=[{"message": str(error)}],
            )
            return
        self._write_json(HTTPStatus.OK, {"date": canonical_date})

    def _request_path(self) -> str:
        return urlsplit(self.path).path

    def _require_authenticated_user(
        self,
        *,
        request_id: str,
        endpoint_key: str,
    ) -> PersistedUser | None:
        client_ip = self._resolve_client_ip()
        if self._AUTH_RATE_LIMITER.is_limited(client_ip=client_ip, endpoint_key=endpoint_key):
            self._write_auth_error(code="auth_rate_limited", request_id=request_id)
            return None

        token = self._extract_bearer_token()
        if token is None:
            self._write_auth_error(code="auth_missing_token", request_id=request_id)
            return None

        users_store = JsonUsersStore(resolve_users_store_path())
        user = self._resolve_user_for_token(token=token, users_store=users_store)
        if user is not None:
            return user

        self._write_auth_error(code="auth_invalid_token", request_id=request_id)
        return None

    def _resolve_user_for_token(
        self,
        *,
        token: str,
        users_store: JsonUsersStore,
    ) -> PersistedUser | None:
        for user in users_store.list_users():
            try:
                verification = verify_bearer_token(token=token, verifier=user.token_verifier)
            except ValidationError:
                continue
            if verification.is_valid:
                return user
        return None

    def _resolve_client_ip(self) -> str:
        remote_ip = self.client_address[0]
        if not _ip_is_trusted_proxy(remote_ip):
            return remote_ip

        forwarded_for = self.headers.get("X-Forwarded-For")
        if forwarded_for is None:
            return remote_ip
        candidate = forwarded_for.split(",")[0].strip()
        if not candidate:
            return remote_ip
        try:
            ip_address(candidate)
        except ValueError:
            return remote_ip
        return candidate

    def _extract_bearer_token(self) -> str | None:
        authorization_header = self.headers.get("Authorization")
        if authorization_header is None:
            return None
        if not authorization_header.startswith("Bearer "):
            return None
        token = authorization_header[len("Bearer ") :].strip()
        if not token:
            return None
        return token

    def _single_query_param(self, name: str) -> str | None:
        query_params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        values = query_params.get(name)
        if values is None:
            return None
        if len(values) != 1:
            raise ValidationError(f"{name}: expected single query parameter")
        return values[0]

    def _read_json_payload(self) -> dict[str, object]:
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
        return dict(parsed)

    def _write_api_error(
        self,
        *,
        status: HTTPStatus,
        code: str,
        message: str,
        request_id: str,
        details: list[dict[str, str]] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        error_payload: dict[str, object] = {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
        if details:
            error_payload["details"] = details
        envelope = ApiErrorEnvelope.model_validate({"error": error_payload})
        self._write_json(
            status,
            envelope.model_dump(mode="json", exclude_none=True),
            headers=headers,
        )

    def _write_auth_error(
        self,
        *,
        code: str,
        request_id: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        defaults = AUTH_ERROR_DEFAULTS[code]
        headers: dict[str, str] | None = None
        retry_after = defaults["retry_after_seconds"]
        if retry_after is not None:
            headers = {"Retry-After": str(retry_after)}
        self._write_api_error(
            status=HTTPStatus(defaults["status"]),
            code=code,
            message=defaults["message"],
            request_id=request_id,
            details=details,
            headers=headers,
        )

    def _write_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", _UI_CONTENT_SECURITY_POLICY)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_javascript(self, source: str) -> None:
        encoded = source.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_json(
        self,
        status: HTTPStatus,
        payload: object,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        if headers:
            for header_name, header_value in headers.items():
                self.send_header(header_name, header_value)
        self.end_headers()
        self.wfile.write(encoded)


def _render_app_shell(active_page: str) -> str:
    content = _PAGE_CONTENT[active_page]
    return _APP_SHELL_TEMPLATE.substitute(
        section_label=content["section_label"],
        title=content["title"],
        description=content["description"],
        content_html=content["content_html"],
        set_user_current="page" if active_page == "set-user" else "false",
        settings_current="page" if active_page == "settings" else "false",
        privacy_current="page" if active_page == "privacy" else "false",
        calculate_current="page" if active_page == "calculate" else "false",
        calendar_current="page" if active_page == "calendar" else "false",
        log_current="page" if active_page == "log" else "false",
    )


def _app_shell_inline_script() -> str:
    template_body = _APP_SHELL_TEMPLATE.template
    start_marker = '<script data-app-shell-inline="true">'
    end_marker = "</script>"
    start_index = template_body.find(start_marker)
    if start_index < 0:
        return ""
    script_start = start_index + len(start_marker)
    end_index = template_body.find(end_marker, script_start)
    if end_index < 0:
        return ""
    script = template_body[script_start:end_index].strip()
    return script.replace("$$", "$") + "\n"


def _error_detail_from_exception(error: Exception) -> dict[str, str]:
    message = str(error).strip()
    if ": " not in message:
        return {"message": message or "Invalid request."}
    field, detail = message.split(": ", maxsplit=1)
    if not field:
        return {"message": detail or "Invalid request."}
    return {"field": field, "message": detail or "Invalid request."}


def _error_detail_from_pydantic_validation(error: PydanticValidationError) -> dict[str, str]:
    first_error = error.errors()[0]
    path = ".".join(str(part) for part in first_error.get("loc", ()))
    message = str(first_error.get("msg", "Invalid response.")).strip()
    if path:
        return {"field": path, "message": message or "Invalid response."}
    return {"message": message or "Invalid response."}


def _calendar_store_path() -> Path:
    configured_path = os.environ.get(CALENDAR_STORE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".mealplan" / "calendar.json"


def _food_log_store_path() -> Path:
    configured_path = os.environ.get(FOOD_LOG_STORE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".mealplan" / "food-log.json"


def _user_calendar_store_path(*, user: PersistedUser) -> Path:
    base_path = _calendar_store_path()
    return resolve_user_partitioned_path(
        storage_directory=base_path.parent,
        email=user.email,
        suffix_filename=base_path.name,
    )


def _user_food_log_store_path(*, user: PersistedUser) -> Path:
    base_path = _food_log_store_path()
    return resolve_user_partitioned_path(
        storage_directory=base_path.parent,
        email=user.email,
        suffix_filename=base_path.name,
    )


def _ip_is_trusted_proxy(candidate_ip: str) -> bool:
    try:
        parsed_ip = ip_address(candidate_ip)
    except ValueError:
        return False
    return any(parsed_ip in network for network in _trusted_proxy_networks())


def _trusted_proxy_networks() -> tuple[IPv4Network | IPv6Network, ...]:
    configured = os.environ.get(TRUSTED_PROXY_CIDRS_ENV, "")
    if not configured.strip():
        return ()
    networks: list[IPv4Network | IPv6Network] = []
    for raw_cidr in configured.split(","):
        cidr = raw_cidr.strip()
        if not cidr:
            continue
        try:
            networks.append(ip_network(cidr, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _calendar_date_from_path(path: str) -> str | None:
    prefix = "/api/v1/calendar/"
    if not path.startswith(prefix):
        return None
    date_key = path.removeprefix(prefix)
    if not date_key or "/" in date_key:
        return None
    return date_key


def _log_uuid_from_path(path: str) -> str | None:
    prefix = "/api/v1/log/"
    if not path.startswith(prefix):
        return None
    entry_uuid = path.removeprefix(prefix)
    if not entry_uuid or "/" in entry_uuid:
        return None
    return entry_uuid


def _is_calendar_not_found_error(error: DomainRuleError) -> bool:
    message = str(error).strip()
    return message.startswith("calendar.") and message.endswith(": meal plan not found")


def _is_log_not_found_error(error: DomainRuleError) -> bool:
    message = str(error).strip()
    return message.startswith("log.") and message.endswith(": entry not found")


def _normalize_calendar_date(date_key: str) -> str:
    try:
        parsed = datetime.strptime(date_key, _DATE_KEY_FORMAT)
    except ValueError as error:
        raise ValidationError("date: expected YYYYMMDD") from error
    canonical = parsed.strftime(_DATE_KEY_FORMAT)
    if canonical != date_key:
        raise ValidationError("date: expected YYYYMMDD")
    return canonical


def run_ui_server() -> None:
    """Start UI mode server and block until SIGINT/SIGTERM shutdown."""
    server = _bind_ui_server()
    host, port = server.server_address[:2]
    host_name = host if isinstance(host, str) else bytes(host).decode("utf-8")
    port_number = int(port)

    print(f"UI available at http://{host_name}:{port_number}/calendar", flush=True)
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
