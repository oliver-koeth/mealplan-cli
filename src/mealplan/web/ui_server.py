"""Local UI mode HTTP server lifecycle and routing."""

from __future__ import annotations

import json
import os
import signal
import socketserver
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from mealplan.application.contracts import MealPlanRequest, MealPlanResponse
from mealplan.application.orchestration import MealPlanCalculationService
from mealplan.application.parsing import parse_contract
from mealplan.infrastructure import JsonCalendarStore
from mealplan.shared.errors import DomainRuleError, ValidationError

UI_HOST = "127.0.0.1"
UI_PORT_START = 8765
UI_PORT_END = 8775
SHUTDOWN_DRAIN_SECONDS = 5.0
UI_PORT_START_ENV = "MEALPLAN_UI_PORT_START"
UI_PORT_END_ENV = "MEALPLAN_UI_PORT_END"
CALENDAR_STORE_PATH_ENV = "MEALPLAN_CALENDAR_STORE_PATH"
_DATE_KEY_FORMAT = "%Y%m%d"

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
      }

      :root[data-theme="light"] {
        color-scheme: light;
      }

      * {
        box-sizing: border-box;
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

      .section-label {
        margin: 0;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--text-subtle);
      }

      .calculate-section-label {
        margin-bottom: 0.7rem;
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
      select {
        width: 100%;
        border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--border) 74%, transparent);
        background: color-mix(in srgb, var(--surface) 93%, #0f172a 7%);
        color: var(--text);
        font: inherit;
        padding: 0.5rem 0.65rem;
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

      .date-input-wrap {
        min-width: 220px;
        flex: 1 1 280px;
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
        border: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
        border-radius: 12px;
        background: linear-gradient(
          150deg,
          color-mix(in srgb, var(--surface) 92%, #1d4ed8 8%),
          color-mix(in srgb, var(--surface-muted) 93%, #0f172a 7%)
        );
        color: var(--text);
        padding: 0.52rem 0.86rem;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }

      .primary-button[disabled] {
        cursor: wait;
        opacity: 0.7;
      }

      .secondary-button {
        font-weight: 500;
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
        display: grid;
        gap: 0.75rem;
        grid-template-columns: repeat(6, minmax(0, 1fr));
      }

      .results-total {
        border-radius: 14px;
        border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
        background: linear-gradient(
          145deg,
          color-mix(in srgb, var(--surface-muted) 96%, #1d4ed8 4%),
          color-mix(in srgb, var(--surface) 95%, #0f172a 5%)
        );
        padding: 0.8rem 0.9rem;
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

      .results-total:nth-child(1) {
        background: linear-gradient(145deg, rgba(37, 99, 235, 0.26), rgba(30, 58, 138, 0.2));
        border-color: rgba(37, 99, 235, 0.5);
      }

      .results-total:nth-child(2) {
        background: linear-gradient(145deg, rgba(5, 150, 105, 0.23), rgba(6, 95, 70, 0.2));
        border-color: rgba(5, 150, 105, 0.45);
      }

      .results-total:nth-child(3) {
        background: linear-gradient(145deg, rgba(124, 58, 237, 0.24), rgba(76, 29, 149, 0.2));
        border-color: rgba(124, 58, 237, 0.45);
      }

      .results-total:nth-child(4) {
        background: linear-gradient(145deg, rgba(217, 119, 6, 0.24), rgba(120, 53, 15, 0.2));
        border-color: rgba(217, 119, 6, 0.45);
      }

      .results-total:nth-child(5) {
        background: linear-gradient(145deg, rgba(190, 24, 93, 0.24), rgba(131, 24, 67, 0.2));
        border-color: rgba(190, 24, 93, 0.45);
      }

      .results-total:nth-child(6) {
        background: linear-gradient(145deg, rgba(8, 145, 178, 0.24), rgba(14, 116, 144, 0.2));
        border-color: rgba(8, 145, 178, 0.45);
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

        .results-totals {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .meal-result-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
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
          <a class="nav-link" href="/calendar" aria-current="$calendar_current">Calendar</a>
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

        const calculateForm = document.querySelector('[data-calculate-form="true"]');
        const calendarForm = document.querySelector('[data-calendar-form="true"]');

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
          const calendarMealsGrid = document.querySelector('[data-calendar-results-meals="true"]');
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
            && calendarMealsGrid
          ) {
            if (!calendarDateControl.value) {
              calendarDateControl.value = toIsoDate(new Date());
            }
            const mealOrder = [
              "breakfast",
              "morning-snack",
              "lunch",
              "afternoon-snack",
              "dinner",
              "evening-snack",
            ];
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

            const renderCalendarResults = (payload) => {
              const totals = [
                ["Total kcal", Number(payload?.total_kcal), "kcal"],
                ["TDEE", Number(payload?.TDEE), "kcal"],
                ["Training kcal", Number(payload?.training_kcal), "kcal"],
                ["Carbs", Number(payload?.carbs_g), "g"],
                ["Fat", Number(payload?.fat_g), "g"],
                ["Protein", Number(payload?.protein_g), "g"],
              ];
              calendarTotalsGrid.innerHTML = "";
              for (const [label, value, unit] of totals) {
                const card = document.createElement("article");
                card.className = "results-total";
                const title = document.createElement("strong");
                title.textContent = label;
                const valueNode = document.createElement("span");
                valueNode.textContent = formatNumber(value) + " " + unit;
                card.appendChild(title);
                card.appendChild(valueNode);
                calendarTotalsGrid.appendChild(card);
              }

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
              calendarMealsGrid.innerHTML = "";
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
                calendarMealsGrid.appendChild(card);
              }
              hideCalendarFeedback();
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
                renderCalendarResults(payload);
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
        const saveErrorSummary = document.querySelector('[data-calculate-save-error-summary="true"]');
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
              headers: {"Content-Type": "application/json"},
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
              headers: {"Content-Type": "application/json"},
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
          <section class="results-state" data-calendar-results-state="true" hidden>
            <section class="form-card results-panel" data-calendar-results="true" hidden>
              <h2>Saved Meal Plan</h2>
              <p class="hint">
                This calendar view is read-only.
              </p>
              <section class="results-totals" data-calendar-results-totals="true"></section>
              <section class="results-meals" data-calendar-results-meals="true"></section>
            </section>
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
        if path in ("/", "/calculate"):
            self._write_html(_render_app_shell("calculate"))
            return
        if path == "/calendar":
            self._write_html(_render_app_shell("calendar"))
            return
        if path == "/settings":
            self._write_html(_render_app_shell("settings"))
            return
        if path == "/api/v1/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
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
        if path != "/api/v1/calculate":
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

    def do_PUT(self) -> None:  # noqa: N802
        path = self._request_path()
        calendar_date = _calendar_date_from_path(path)
        if calendar_date is None:
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "not_found", "message": "Not found"}},
            )
            return

        self._handle_calendar_put(calendar_date)

    def _handle_calendar_get(self, date_key: str) -> None:
        request_id = str(uuid4())
        store = JsonCalendarStore(_calendar_store_path())
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
        store = JsonCalendarStore(_calendar_store_path())
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
        calendar_current="page" if active_page == "calendar" else "false",
    )


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


def _calendar_date_from_path(path: str) -> str | None:
    prefix = "/api/v1/calendar/"
    if not path.startswith(prefix):
        return None
    date_key = path.removeprefix(prefix)
    if not date_key or "/" in date_key:
        return None
    return date_key


def _is_calendar_not_found_error(error: DomainRuleError) -> bool:
    message = str(error).strip()
    return message.startswith("calendar.") and message.endswith(": meal plan not found")


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
