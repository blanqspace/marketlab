LINT_TARGETS := scripts/env_check.py tools/verify_telegram_env.py
FORMAT_TARGETS := scripts/env_check.py tools/tg_poller.py tools/verify_telegram_env.py src/marketlab/tools src/marketlab/ui src/marketlab/daemon/worker.py

.PHONY: venv install env-check lint lint-all lint-report format type test security run-supervisor run-worker run-poller run-dashboard run-all-tmux ci

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PY := $(if $(wildcard $(BIN)/python),$(BIN)/python,$(PYTHON))

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e .[dev]

env-check:
	PYTHONPATH=src $(PY) scripts/env_check.py

lint:
	$(PY) -m ruff check $(LINT_TARGETS)

lint-all:
	$(PY) -m ruff check .

lint-report:
	mkdir -p reports
	$(PY) -m ruff check --statistics --output-format concise . | tee reports/lint-report.txt || true

format:
	$(PY) -m black --check $(FORMAT_TARGETS)

type:
	$(PY) -m mypy --strict

test:
	IBKR_LIVE=0 PYTHONPATH=src $(PY) -m pytest -q

security:
	$(PY) -m bandit -q -r src --severity-level medium --confidence-level medium

run-supervisor:
	PYTHONPATH=src $(PY) -m marketlab.supervisor

run-worker:
	PYTHONPATH=src $(PY) -m marketlab.worker

run-poller:
	PYTHONPATH=src $(PY) -m marketlab.tools.tg_poller

run-dashboard:
	PYTHONPATH=src $(PY) -m marketlab.ui.dashboard

run-all-tmux:
	bash tools/tmux_marketlab.sh

ci:
	$(PY) -m ruff check .
	$(PY) -m black --check .
	$(PY) -m mypy --strict
	PYTHONPATH=src $(PY) -m pytest -q --junitxml=pytest.xml
