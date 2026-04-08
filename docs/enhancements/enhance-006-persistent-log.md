# Enhancement Brief: enhance-006 Persistent Log

## Problem statement
Users can calculate plans and persist date-keyed calendar results, but there is no persistent food-log workflow to capture what was actually eaten and reuse prior entries. This blocks practical day-to-day logging and makes both CLI and web flows less useful for repeated meals.

The enhancement adds a UUID-keyed persistent food-log capability exposed through CLI, REST, and the local web `/log` page.

## Goals
- Add deterministic file-backed persistence for food-log entries.
- Support create and update by UUID from CLI and REST.
- Support optional-filter search for entry reuse.
- Provide a dedicated `/log` UI flow for entry and search interactions.

## In scope
- Application contracts:
  - canonical upsert request contract with optional `uuid` and default `quantity=1.0`
  - canonical search request contract with optional `date`, `name`, `meal`
  - canonical response contract with `uuid`, `date`, `meal`, `name`, `kcal`, `carbs`, `fat`, `protein`, `fiber`
  - canonical date validation (`YYYYMMDD`) at boundary parsing points
- Infrastructure persistence:
  - dedicated JSON store for food logs (`~/.mealplan/food-log.json` default)
  - create flow with backend-generated UUID
  - update flow by UUID with deterministic not-found error for unknown UUID
  - quantity multiplier applied to persisted nutrition values (`kcal`, `carbs`, `fat`, `protein`, `fiber`)
  - quantity is not persisted as a stored field
  - auto-create storage file when missing
- CLI:
  - `mealplan log` upsert command with required field flags and optional `--quantity`
  - `mealplan log --json` one-shot payload mode (exclusive vs field flags)
  - `uuid` presence determines update path; absence determines create path
  - `mealplan log search` with optional `--date`, `--name`, `--meal` filters
  - deterministic errors for unknown UUID updates
- REST/UI server:
  - `POST /api/v1/log`
  - `PUT /api/v1/log/{uuid}`
  - `GET /api/v1/log/search`
  - structured API error envelopes for validation/not-found/runtime paths
- Web UI:
  - top-level `/log` page and nav item
  - entry region with Add/Save mode switching and success callout
  - search region with optional filters and result list rendering
  - result interactions: expand/collapse details, Add to form, Edit in form

## Out of scope
- Remote/cloud sync or multi-user access.
- Barcode scanning, nutrition lookup integrations, or external food databases.
- Historical audit/versioning for updates to the same UUID.
- Batch import/export beyond simple JSON-file persistence.

## Constraints and assumptions
- Canonical date format is `YYYYMMDD` across CLI, REST, contracts, and persistence.
- Food-log persistence is local file-based JSON and optimized for single-process local usage.
- Search semantics are optional-AND: all provided filters must match.
- Name matching is case-insensitive substring.
- Search ordering is newest-first by date.
- REST `PUT /api/v1/log/{uuid}` treats route UUID as canonical.

## Definition of done
- Contracts for log upsert/search/entry are implemented and validated.
- UUID-keyed JSON log store supports create/update/search behavior with deterministic errors.
- CLI `mealplan log` and `mealplan log search` are implemented with documented help behavior.
- REST log create/update/search endpoints are implemented with canonical envelopes.
- `/log` page supports entry and result workflows including Add/Save/Edit interactions.
- Tests cover store, CLI, API, and UI shell wiring for the persistent-log behavior.
- Architecture and README docs reflect canonical log contracts, routes, and command usage.

## Open questions
- None for this enhancement scope.
