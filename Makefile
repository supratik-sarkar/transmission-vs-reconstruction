.PHONY: help install dev test lint format typecheck check selftest privacy secrets stages baselines prereg contract toolchain clean

help:
	@echo "install    editable install"
	@echo "dev        editable install with dev extras"
	@echo "check      lint + typecheck + tests + privacy scan"
	@echo "selftest   deterministic design invariants"
	@echo "privacy    fail if tracked files leak private material"

install:
	python -m pip install -e .

dev:
	python -m pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

selftest:
	handoff self-test

privacy:
	handoff privacy-scan --root .

secrets:
	detect-secrets scan --all-files --exclude-files '(^|/)\.git/' > /dev/null && echo "secret scan complete"

stages:
	handoff stages

baselines:
	handoff baselines

toolchain:
	bash scripts/toolchain_report.sh

prereg:
	python scripts/prereg_accounting.py

contract:
	@echo "usage: python scripts/map_manuscript_contract.py --tex <file>.tex --bib <file>.bib"

check: lint typecheck test privacy prereg

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
