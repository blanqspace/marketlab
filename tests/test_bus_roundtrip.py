from __future__ import annotations

import os
import sqlite3

from marketlab.daemon.worker import Worker, WorkerConfig
from marketlab.ipc import bus


def test_worker_processes_pause(monkeypatch, tmp_path):
    db_path = tmp_path / "ctl.db"
    monkeypatch.setenv(bus.DB_ENV, str(db_path))
    bus.bus_init()

    worker = Worker(cfg=WorkerConfig(two_man_rule=False, confirm_strict=True, ttl_seconds=300))

    cmd_id = bus.enqueue("state.pause", {}, source="test")
    processed = worker.process_available()
    assert processed == 1

    with sqlite3.connect(str(db_path)) as con:
        status = con.execute("SELECT status FROM commands WHERE cmd_id=?", (cmd_id,)).fetchone()
        assert status is not None and status[0] == "DONE"

    events = bus.tail_events(5)
    assert any(
        ev.message == "state.changed" and ev.fields.get("state") == "PAUSED" for ev in events
    )
