.PHONY: help install dev test lint format typecheck check selftest privacy secrets stages baselines prereg contract toolchain api web demo mock-e2e test-python test-web e2e policy-test architecture-check clean

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

api:
	HANDOFF_APP_MODE=$${HANDOFF_APP_MODE:-DEMO_MODE} python -m uvicorn handoff_api.app:create_app --factory --host 127.0.0.1 --port 8099

web:
	cd apps/web && npm run dev

demo:
	@echo "1) make api    2) make web    3) open http://127.0.0.1:5173"

mock-e2e:
	python -c "from handoff_fidelity.orchestration.mock_pipeline import run_mock_pipeline as r; x=r(seed=2); print(x.marker); print(x.state.decomposition)"

test-python: test

test-web:
	cd apps/web && npm run lint && npm run typecheck && npm run test && npm run build

e2e:
	cd apps/web && npm run e2e

policy-test:
	@command -v opa >/dev/null 2>&1 && opa test policies/ || echo "OPA_HOST_VERIFICATION_REQUIRED: opa binary not found"

architecture-check:
	python -c "from handoff_fidelity.orchestration.graph import topology_description as t; import json; print(json.dumps(t(), indent=2))"
	python scripts/prereg_accounting.py

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
