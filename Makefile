UV ?= .venv/bin/uv

.PHONY: quality lint typecheck test

quality: lint typecheck test

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy --strict src

test:
	$(UV) run pytest
