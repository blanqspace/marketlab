from __future__ import annotations

import os

from marketlab.ipc import bus
from marketlab.core.status import events_tail_agg


def setup_db(tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()
    return db


def test_events_tail_aggregation(tmp_path):
    db = setup_db(tmp_path)
    # Emit duplicate events with identical fields
    for _ in range(5):
        bus.emit("warn", "orders.confirm.pending", token="XYZ123", source="cli")
    for _ in range(3):
        bus.emit("warn", "orders.confirm.pending", token="XYZ123", source="cli")
    # And a different one
    bus.emit("ok", "state.changed", state="RUN")

    ag = events_tail_agg(db, n=100)
    # find the aggregated entry
    found = None
    for e in ag:
        if (
            e.get("message") == "orders.confirm.pending"
            and (e.get("fields") or {}).get("token") == "XYZ123"
        ):
            found = e
            break
    assert found is not None
    assert int(found.get("count", 0)) >= 8
