.PHONY: setup lint format typecheck test guards ci

setup:  ## Install the workspace and the git hooks
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

guards:  ## Data-policy checks: no raw market data, licence gate
	uv run python tools/ci/check_raw_data.py
	uv run python tools/ci/licence_gate.py

ci: lint typecheck test guards
