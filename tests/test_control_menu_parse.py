from __future__ import annotations

from src.marketlab.control_menu import _parse_selector
from src.marketlab.orders.schema import OrderTicket
from src.marketlab.orders import store
from src.marketlab.ipc import bus
import os, sys, subprocess


def test_parse_selector_number_and_token():
    assert _parse_selector("1") == 1
    assert _parse_selector("ABC7QK") == "ABC7QK"


def test_parse_selector_empty_raises():
    import pytest

    with pytest.raises(Exception):
        _ = _parse_selector("")


def _with_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_control_menu_lazy_confirm_selects_number(tmp_path):
    _with_tmp_db(tmp_path)
    # One pending ticket
    t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
    store.put_ticket(t)
    pend = store.get_pending(limit=1)
    tok = pend[0]["token"]
    # Open control-menu, choose 4 (list), then 1, then exit 9
    p = subprocess.run(
        [sys.executable, "-m", "marketlab", "control-menu"],
        input="4\n1\n9\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert p.returncode == 0
    assert f"OK: orders.confirm -> {tok}" in p.stdout


def test_control_menu_pagination_next_previous(tmp_path):
    _with_tmp_db(tmp_path)
    # Create 12 pending tickets to ensure pagination
    tokens = []
    for i in range(12):
        t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
        store.put_ticket(t)
    pend = store.get_pending(limit=20)
    assert len(pend) >= 12
    tok_page2_first = pend[10]["token"]
    p = subprocess.run(
        [sys.executable, "-m", "marketlab", "control-menu"],
        input="4\nn\n1\n9\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert p.returncode == 0
    assert f"OK: orders.confirm -> {tok_page2_first}" in p.stdout


def test_control_menu_short_form_token_direct(tmp_path):
    _with_tmp_db(tmp_path)
    t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
    store.put_ticket(t)
    pend = store.get_pending(limit=1)
    tok = pend[0]["token"]
    p = subprocess.run(
        [sys.executable, "-m", "marketlab", "control-menu"],
        input=f"4 {tok}\n9\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert p.returncode == 0
    assert f"OK: orders.confirm -> {tok}" in p.stdout
