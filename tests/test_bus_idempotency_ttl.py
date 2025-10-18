from __future__ import annotations

import os
import sqlite3
import time

from marketlab.ipc import bus


def with_tmp_db(tmp_path):
    db = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db)
    bus.bus_init()
    return db


def _phases(db_path: str, cmd_id: str) -> list[str]:
    with sqlite3.connect(db_path) as con:
        cur = con.execute(
            "SELECT phase FROM command_audit WHERE cmd_id=? ORDER BY id ASC",
            (cmd_id,),
        )
        return [row[0] for row in cur.fetchall()]


def test_request_id_idempotency(tmp_path):
    db = with_tmp_db(tmp_path)
    cid1 = bus.enqueue(
        "state.pause",
        {"reason": "dup"},
        source="cli",
        request_id="req-123",
        actor_id="alice",
    )
    cid2 = bus.enqueue(
        "state.pause",
        {"reason": "dup"},
        source="cli",
        request_id="req-123",
        actor_id="alice",
    )
    assert cid1 == cid2

    with sqlite3.connect(str(db)) as con:
        row = con.execute("SELECT COUNT(1) FROM commands WHERE request_id='req-123'").fetchone()
        assert row and row[0] == 1

    phases = _phases(str(db), cid1)
    assert "enqueue" in phases


def test_ttl_expiry_marks_expired(tmp_path):
    db = with_tmp_db(tmp_path)
    cid = bus.enqueue(
        "orders.pending",
        {},
        source="cli",
        ttl_sec=1,
        actor_id="cli-user",
        request_id="req-expire",
    )
    with sqlite3.connect(str(db)) as con:
        now = int(time.time())
        con.execute(
            "UPDATE commands SET created_at=?, available_at=? WHERE cmd_id=?",
            (now - 10, now - 10, cid),
        )

    got = bus.next_new(now=int(time.time()))
    assert got is None

    with sqlite3.connect(str(db)) as con:
        status = con.execute("SELECT status FROM commands WHERE cmd_id=?", (cid,)).fetchone()
        assert status and status[0] == "EXPIRED"

    events = bus.tail_events(5)
    assert any(ev.message == "command.expired" and ev.fields.get("cmd_id") == cid for ev in events)
    phases = _phases(str(db), cid)
    assert "expired" in phases
