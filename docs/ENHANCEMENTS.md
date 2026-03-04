# Enhancements Workflow

This document defines the default workflow for incremental feature enhancements in this repository.

## 1. Goal

Use a single enhancement brief as the authored source of truth, then derive implementation artifacts (`PRD` and Ralph `prd.json`) without manually editing all docs for each change.

## 2. Naming and Scope

- Enhancement IDs are sequential: `enhance-001`, `enhance-002`, ...
- Enhancement slugs use kebab-case.
- Each enhancement must be scoped so it can be implemented in one Ralph story iteration flow (no multi-phase decomposition inside one enhancement).
- Prefer `enhance-*` naming for new work; existing `phase-*` history remains unchanged.

## 3. Canonical Files and Directories

- Authored enhancement brief:
  - `docs/enhancements/enhance-###-<slug>.md`
- Generated PRD:
  - `tasks/prd-enhance-###-<slug>.md`
- Active Ralph backlog input:
  - `scripts/ralph/prd.json`
- Archived Ralph run artifacts:
  - `scripts/ralph/archive/YYYY-MM-DD-enhance-###-<slug>/prd.json`
  - `scripts/ralph/archive/YYYY-MM-DD-enhance-###-<slug>/progress.txt`

## 4. Standard Workflow

1. Write one enhancement brief in `docs/enhancements/`.
2. Generate a PRD from that brief using the PRD skill into `tasks/prd-enhance-###-<slug>.md`.
3. Convert the PRD to Ralph format using the Ralph skill and write the active backlog to `scripts/ralph/prd.json`.
4. Run Ralph from `scripts/ralph/prd.json`.
5. Archive `prd.json` and `progress.txt` under `scripts/ralph/archive/YYYY-MM-DD-enhance-###-<slug>/`.

## 5. Brief Template (Required Sections)

Each `docs/enhancements/enhance-###-<slug>.md` should contain:

- Title and enhancement ID
- Problem statement
- Goals
- In scope
- Out of scope
- Constraints and assumptions
- Definition of done
- Open questions (optional)

Keep content concise and implementation-oriented so downstream PRD stories stay right-sized.

## 6. PRD and Ralph Rules

- PRD stories must be explicit, verifiable, and small.
- Ralph conversion must preserve dependency-safe story ordering.
- Every story must include `Typecheck passes`.
- Add `Tests pass` where logic is testable.
- Add `Verify in browser using dev-browser skill` for UI-affecting stories.

## 7. Documentation Update Policy

- Do not rewrite all core docs per enhancement.
- Update core docs (`docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/MODEL.md`, `docs/PLAN.md`) only when the enhancement changes canonical behavior/contracts/architecture.
- If no canonical contract changes occur, keep updates limited to enhancement artifacts and Ralph archive outputs.
