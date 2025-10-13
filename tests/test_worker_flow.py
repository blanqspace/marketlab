from __future__ import annotations
import os
from pathlib import Path

from marketlab.ipc import bus
from marketlab.daemon.worker import Worker, load_config, WorkerConfig


def with_tmp_db(tmp_path) -> Path:
    db = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db)
    bus.bus_init()
    return db


def test_worker_processes_state_and_orders_with_two_man_rule(tmp_path, monkeypatch):
    with_tmp_db(tmp_path)
    # enable two-man rule explicitly
    monkeypatch.setenv("ORDERS_TWO_MAN_RULE", "1")
    monkeypatch.setenv("CONFIRM_STRICT", "1")

    w = Worker(load_config())

    # simple state command
    cid = bus.enqueue("state.pause", {}, source="cli")
    assert w.process_available() == 1
    ev = bus.tail_events(1)[0]
    assert ev.message in ("state.changed",)
    assert ev.level == "ok"

    # first approval from telegram -> pending
    order_id = "ORDER-XYZ"
    bus.enqueue("orders.confirm", {"id": order_id}, source="telegram")
    w.process_available()
    ev = bus.tail_events(1)[0]
    assert ev.message == "orders.confirm.pending"
    assert ev.level == "warn"

    # second approval from cli -> ok
    bus.enqueue("orders.confirm", {"id": order_id}, source="cli")
    w.process_available()
    ev = bus.tail_events(1)[0]
    assert ev.message == "orders.confirm.ok"
    assert ev.level == "ok"
