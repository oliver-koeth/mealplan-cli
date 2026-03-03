# Release Readiness Checklist

Use this checklist before publishing a release candidate.

## 1. Baseline and environment

- [ ] Working tree is clean (`git status --short` has no output).
- [ ] Dependencies are synced:
  ```bash
  uv sync --dev
  ```
  Expected outcome: environment resolves without errors.

## 2. Quality and snapshot gates

- [ ] Run all local quality checks:
  ```bash
  make quality
  ```
  Expected outcome: lint, typecheck, and tests pass.

- [ ] Verify golden snapshot suites (CLI + application):
  ```bash
  uv run pytest tests/golden
  ```
  Expected outcome: all snapshot tests pass with no fixture drift.

## 3. Packaging gates

- [ ] Build and validate source + wheel artifacts:
  ```bash
  make package-check
  ```
  Expected outcome:
  - `dist/` contains exactly one `.whl` and one `.tar.gz`
  - package metadata (`Name`, `Version`) is valid
  - wheel includes `mealplan` console entry point

## 4. Installability smoke gates

- [ ] Verify isolated install workflow from built wheel:
  ```bash
  make install-smoke-check
  ```
  Expected outcome:
  - wheel installs into a fresh temp virtualenv
  - `mealplan --help` succeeds
  - `python -m mealplan --help` succeeds
  - one `mealplan calculate ... --format json` smoke command succeeds

## 5. CI gate verification

- [ ] Confirm latest GitHub Actions CI run for target commit is green.
  Expected outcome:
  - `quality` job passes:
    - Ruff
    - MyPy
    - Pytest golden snapshot suites (`tests/golden`)
    - Pytest non-golden suites (`--ignore=tests/golden`)
  - `package-build` job passes:
    - package artifact verification script succeeds
    - `dist/*` workflow artifact is uploaded
  - `install-smoke` job passes:
    - `dist/*` artifact download succeeds
    - install workflow verification script succeeds
  - failure logs clearly identify one of:
    - snapshot drift or test failure
    - package metadata/entry-point build failure
    - wheel install or post-install smoke command failure

## 6. Versioning and release notes (first usable release)

- [ ] Versioning policy for first usable release:
  - use a clear stable tag starting at `v1.0.0`
  - if not yet stable, use pre-release tags (`v1.0.0-rc.1`, `v1.0.0-rc.2`, ...)

- [ ] Prepare release notes containing:
  - scope summary (CLI behavior, snapshot coverage, packaging/install readiness)
  - upgrade/install instructions from wheel
  - known limitations and deferred items

- [ ] Validate release notes map to shipped behavior by running:
  ```bash
  uv run mealplan --help
  uv run mealplan calculate --help
  ```
  Expected outcome: documented flags and examples match actual CLI help output.

## 7. Final go/no-go

- [ ] Re-run critical gates in order:
  ```bash
  make quality
  make package-check
  make install-smoke-check
  ```
- [ ] If all pass, proceed with tag and release publication.
