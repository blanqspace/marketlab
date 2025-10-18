from __future__ import annotations
import os
import time
import sqlite3
from pathlib import Path
import random

from marketlab.ipc import bus


def with_tmp_db(tmp_path):
    db = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db)
    bus.bus_init()
    return db


def test_enqueue_dequeue_order(tmp_path):
    with_tmp_db(tmp_path)
    cid = bus.enqueue("state.pause", {"reason": "test"}, source="cli")
    assert isinstance(cid, str)
    got = bus.next_new()
    assert got is not None
    assert got.cmd_id == cid
    assert got.cmd == "state.pause"
    bus.mark_done(cid)


def test_dedupe_returns_same_cmd_id(tmp_path):
    with_tmp_db(tmp_path)
    cid1 = bus.enqueue("orders.confirm", {"id": "X"}, source="cli", dedupe_key="orders:confirm:X")
    cid2 = bus.enqueue("orders.confirm", {"id": "X"}, source="cli", dedupe_key="orders:confirm:X")
    assert cid1 == cid2


def test_ttl_and_available_at(tmp_path):
    with_tmp_db(tmp_path)
    # enqueue with available_at in the future by using backoff
    cid = bus.enqueue("noop", {}, source="cli", ttl_sec=1)
    # Move command into the future artificially
    bus.mark_error(cid, "backoff", retry_backoff_sec=2)
    assert bus.next_new(now=int(time.time())) is None
    # After backoff passes, it should be visible
    t = int(time.time()) + 3
    got = bus.next_new(now=t)
    assert got is not None and got.cmd_id == cid


def test_concurrency_busy(tmp_path):
    import threading, time as _t

    db = with_tmp_db(tmp_path)
    # Hold a transaction to simulate busy briefly, then release in background
    con = sqlite3.connect(str(db), timeout=0.1, check_same_thread=False)
    con.execute("BEGIN IMMEDIATE")

    def release():
        _t.sleep(0.2)
        try:
            con.rollback()
        except Exception:
            pass

    threading.Thread(target=release, daemon=True).start()
    # enqueue should wait and then succeed
    cid = bus.enqueue("x", {}, source="cli")
    assert isinstance(cid, str)
