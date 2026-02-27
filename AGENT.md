# AGENT.md

## Purpose

This file is for autonomous coding agents working in this repository.  
It defines execution workflow and where to find authoritative project rules without duplicating product specs.

## Canonical References (Do Not Rephrase Here)

- Product requirements: `docs/REQUIREMENTS.md`
- Architecture and layer boundaries: `docs/ARCHITECTURE.md`
- Domain model and invariants: `docs/MODEL.md`
- Build sequencing: `docs/PLAN.md`
- Human contributor workflow: `CONTRIBUTING.md`

When in doubt, update those source docs instead of expanding this file.

## Current State Snapshot

- Project is in **Phase 1 (Foundation and Scaffolding)** from `docs/PLAN.md`.
- Ralph backlog file: `scripts/ralph/prd.json`
- Branch target in backlog: `ralph/phase-1-foundation-scaffolding`
- As of this snapshot, stories `US-001` through `US-008` are marked complete.

## Agent Execution Rules

1. Work from `scripts/ralph/prd.json` in ascending `priority`.
2. Keep edits scoped to the active story; avoid bundling unrelated refactors.
3. Preserve architectural import direction (see `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`).
4. Run quality gates locally before marking a story complete:
   - `make quality`
5. After completing a story:
   - set that story's `passes` to `true` in `scripts/ralph/prd.json`
   - append a short entry to `scripts/ralph/progress.txt` (what changed, files touched, checks run)
6. If a story reveals reusable repo-level conventions, update this file briefly.
7. Keep CI quality gates in `.github/workflows/ci.yml` aligned with local `make quality` commands.
8. For Phase 2+ contract work, keep domain enum values centralized in `src/mealplan/domain/enums.py` and import from `mealplan.domain.enums`.

## Ralph Runner

- Preflight: `./scripts/ralph/doctor.sh`
- Execute loop: `./scripts/ralph/ralph.sh <max_iterations>`

## Out of Scope for Phase 1

Do not implement nutrition business logic yet (energy/macros/periodization).  
That starts in later phases defined in `docs/PLAN.md`.
