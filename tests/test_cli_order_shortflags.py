from __future__ import annotations

import os, sys, subprocess, json
from src.marketlab.orders.schema import OrderTicket
from src.marketlab.orders import store
from src.marketlab.ipc import bus


def with_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_cli_orders_confirm_shortflags(tmp_path):
    with_tmp_db(tmp_path)
    # ensure one pending ticket
    t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
    store.put_ticket(t)
    pending = store.get_pending(limit=1)
    token = pending[0]["token"]
    # by --n
    out = subprocess.run(
        [sys.executable, "-m", "marketlab", "orders", "confirm", "--n", "1"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 0
    assert out.stdout.strip().startswith("OK: orders.confirm -> ")
    # by --token
    out2 = subprocess.run(
        [sys.executable, "-m", "marketlab", "orders", "confirm", "--token", token],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out2.returncode == 0
    assert out2.stdout.strip().startswith("OK: orders.confirm -> ")
    # by --last
    out3 = subprocess.run(
        [sys.executable, "-m", "marketlab", "orders", "confirm", "--last"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out3.returncode == 0
    assert out3.stdout.strip().startswith("OK: orders.confirm -> ")
