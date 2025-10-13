from __future__ import annotations

import os
import sqlite3
import time

from marketlab.ipc import bus
from marketlab.core import status as st
from marketlab.orders.schema import OrderTicket
from marketlab.orders.store import put_ticket, set_state


def setup_db(tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()
    return db


def test_recent_cmd_counts_and_queue_depth(tmp_path):
    db = setup_db(tmp_path)
    now = int(time.time())
    # Insert a few commands via SQL to control available_at and status
    con = sqlite3.connect(db)
    try:
        # NEW within window
        con.execute(
            "INSERT INTO commands (cmd_id, cmd, args, source, status, available_at) VALUES (?,?,?,?, 'NEW', ?)",
            ("c1", "state.pause", "{}", "test", now - 60),
        )
        # DONE within window
        con.execute(
            "INSERT INTO commands (cmd_id, cmd, args, source, status, available_at) VALUES (?,?,?,?, 'DONE', ?)",
            ("c2", "state.resume", "{}", "test", now - 120),
        )
        # ERROR within window
        con.execute(
            "INSERT INTO commands (cmd_id, cmd, args, source, status, available_at) VALUES (?,?,?,?, 'ERROR', ?)",
            ("c3", "noop", "{}", "test", now - 10),
        )
        # OLD outside window
        con.execute(
            "INSERT INTO commands (cmd_id, cmd, args, source, status, available_at) VALUES (?,?,?,?, 'NEW', ?)",
            ("c4", "noop", "{}", "test", now - 10_000),
        )
        con.commit()
    finally:
        con.close()

    counts = st.recent_cmd_counts(db, window_sec=300)
    assert counts["NEW"] >= 1
    assert counts["DONE"] >= 1
    assert counts["ERROR"] >= 1
    # queue depth counts NEW commands regardless of window
    qd = st.queue_depth(db)
    assert isinstance(qd, int)
    assert qd >= 2  # c1 and c4 are NEW


def test_orders_summary_kpis(tmp_path, monkeypatch):
    db = setup_db(tmp_path)
    # Create orders: 2 pending, 1 confirmed, 1 rejected
    t1 = OrderTicket.new("AAPL", "BUY", 1, "MARKET", None, None, None, ttl_sec=120)
    put_ticket(t1)
    t2 = OrderTicket.new("MSFT", "SELL", 2, "LIMIT", 100.0, None, None, ttl_sec=180)
    put_ticket(t2)
    t3 = OrderTicket.new("TSLA", "BUY", 1, "MARKET", None, None, None, ttl_sec=60)
    put_ticket(t3)
    set_state(t3.id, "CONFIRMED")
    t4 = OrderTicket.new("GOOG", "SELL", 1, "MARKET", None, None, None, ttl_sec=60)
    put_ticket(t4)
    set_state(t4.id, "REJECTED")

    summ = st.orders_summary(db)
    assert summ["pending"] >= 2
    assert summ["confirmed"] >= 1
    assert summ["rejected"] >= 1
    assert isinstance(summ["avg_ttl_left"], float)
    assert isinstance(summ["two_man_pending_count"], int)

