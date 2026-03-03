UV ?= .venv/bin/uv

.PHONY: quality lint typecheck test package-check install-smoke-check

quality: lint typecheck test

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy --strict src

test:
	$(UV) run pytest

package-check:
	$(UV) run python scripts/checks/verify_package_artifacts.py

install-smoke-check:
	$(UV) run python scripts/checks/verify_install_workflow.py
