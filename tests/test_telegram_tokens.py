from __future__ import annotations

import os
from marketlab.orders.schema import OrderTicket
from marketlab.orders import store
from marketlab.services.telegram_usecases import build_main_menu, handle_callback
from marketlab.ipc import bus


def setup_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_telegram_buttons_and_callbacks(tmp_path):
    setup_tmp_db(tmp_path)
    # ensure there is a pending order
    t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
    store.put_ticket(t)
    tok = store.get_pending(limit=1)[0]["token"]

    menu = build_main_menu()
    # Check that token appears in any button text
    texts = [btn["text"] for row in menu["inline_keyboard"] for btn in row]
    assert any(tok in text for text in texts)

    # Callback confirm_token enqueues orders.confirm
    handle_callback({"action": "confirm_token", "token": tok})
    cmd = bus.next_new()
    assert cmd is not None
    assert cmd.cmd == "orders.confirm"
    bus.mark_done(cmd.cmd_id)

    # Callback reject_token enqueues orders.reject
    handle_callback({"action": "reject_token", "token": tok})
    cmd2 = bus.next_new()
    assert cmd2 is not None
    assert cmd2.cmd == "orders.reject"
    bus.mark_done(cmd2.cmd_id)
