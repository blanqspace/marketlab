from __future__ import annotations
import os
from pathlib import Path

from src.marketlab.ipc import bus


def with_tmp_db(tmp_path) -> Path:
    db = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db)
    bus.bus_init()
    return db


def test_enqueue_next_mark_done_and_error(tmp_path):
    with_tmp_db(tmp_path)
    cid = bus.enqueue("state.pause", {}, source="cli")
    assert isinstance(cid, str)

    c = bus.next_new()
    assert c is not None
    assert c.cmd_id == cid
    assert c.cmd == "state.pause"

    bus.mark_done(cid)
    assert bus.next_new() is None

    cid2 = bus.enqueue("noop", {}, source="cli")
    assert bus.next_new() is not None
    bus.mark_error(cid2, "fail")
    assert bus.next_new() is None


def test_emit_and_tail_events(tmp_path):
    with_tmp_db(tmp_path)
    bus.emit("info", "hello", a=1)
    events = bus.tail_events(5)
    assert len(events) >= 1
    ev = events[0]
    assert ev.level in ("info", "ok", "warn", "error")
    # our bus stores message and fields
    assert hasattr(ev, "message")
    assert isinstance(ev.fields, dict)

