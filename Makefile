LINT_TARGETS := scripts/env_check.py tools/verify_telegram_env.py
FORMAT_TARGETS := scripts/env_check.py tools/tg_poller.py tools/verify_telegram_env.py src/marketlab/tools src/marketlab/ui src/marketlab/daemon/worker.py

.PHONY: venv install env-check lint lint-all lint-report format type test security run-supervisor run-worker run-poller run-dashboard run-all-tmux e2e ci

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

e2e:
	IPC_DB=runtime/e2e.db PYTHONPATH=src $(PY) - <<'PY'
import os
from marketlab.ipc import bus
from marketlab.daemon.worker import Worker
from marketlab.orders import store as orders
from marketlab.orders.schema import OrderTicket

db = os.environ.get("IPC_DB", "runtime/e2e.db")
os.environ[bus.DB_ENV] = db
bus.bus_init()
worker = Worker()

# seed order to exercise stop.now path
orders.put_ticket(OrderTicket.new("E2E", "BUY", 1.0, "MARKET", None, None, None))

bus.enqueue("state.pause", {}, source="e2e")
worker.process_available()
bus.enqueue("state.resume", {}, source="e2e")
worker.process_available()
bus.enqueue("stop.now", {}, source="e2e")
worker.process_available()

events = bus.tail_events(10)
states = [e.fields.get("state") for e in events if e.message == "state.changed"]
assert "RUN" in states, "resume missing"
assert any(e.message == "stop.now" for e in events), "stop.now not executed"
print("e2e ok")
PY
	@echo "E2E run complete"

ci:
	$(PY) -m ruff check .
	$(PY) -m black --check .
	$(PY) -m mypy --strict
	PYTHONPATH=src $(PY) -m pytest -q --junitxml=pytest.xml
