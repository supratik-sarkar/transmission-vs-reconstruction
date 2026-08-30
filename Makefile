.PHONY: install dev test lint typecheck check doctor self-test dry-run zip

install:
	python -m pip install -e .

dev:
	python -m pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy src

check: lint typecheck test

doctor:
	handoff doctor

self-test:
	handoff self-test

dry-run:
	handoff stage1 --dry-run

zip:
	cd .. && zip -r transmission-vs-reconstruction.zip transmission-vs-reconstruction -x '*.git*' -x '*__pycache__*'
