.PHONY: install lint format type test security ci

PYTHON ?= python

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black --check .

type:
	$(PYTHON) -m mypy marketlab.tui marketlab.worker marketlab.daemon.worker

test:
	IBKR_LIVE=0 $(PYTHON) -m pytest -q

security:
	$(PYTHON) -m bandit -q -r src --severity-level medium --confidence-level medium

ci: lint format type test
