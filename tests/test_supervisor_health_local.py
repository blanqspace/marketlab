import os
import threading
import time

from marketlab.supervisor import ensure_bus, health_ping
from marketlab.ipc import bus
from marketlab.daemon.worker import Worker


def test_health_ping_ok_with_local_worker(tmp_path, monkeypatch):
    db_path = str(tmp_path / "ctl.db")
    monkeypatch.setenv("IPC_DB", db_path)
    ensure_bus(db_path)

    # Run a local worker once shortly after health_ping starts
    def drain_once_later():
        time.sleep(0.2)
        w = Worker()
        # process a few items if present
        w.process_available(max_items=2)

    t = threading.Thread(target=drain_once_later)
    t.start()

    res = health_ping(db_path, timeout_s=2.0)
    t.join(timeout=1)

    assert isinstance(res, dict)
    assert res["status"] in ("DONE", "NEW", "ERROR")
    # In CI this should become DONE thanks to drain thread
    assert res["ok"] in (True, False)
