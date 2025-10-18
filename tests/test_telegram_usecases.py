from __future__ import annotations

import os
from marketlab.ipc import bus
from marketlab.services.telegram_usecases import handle_callback


def setup_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_handle_callback_confirm_reject_n(tmp_path):
    setup_tmp_db(tmp_path)
    # With token-based callback
    from marketlab.orders import store as _orders

    tok = _orders.get_pending(limit=1)[0]["token"]
    handle_callback({"action": "confirm_token", "token": tok})
    cmd = bus.next_new()
    assert cmd is not None
    assert cmd.cmd == "orders.confirm"
    bus.mark_done(cmd.cmd_id)

    handle_callback({"action": "reject_token", "token": tok})
    cmd2 = bus.next_new()
    assert cmd2 is not None
    assert cmd2.cmd == "orders.reject"
    bus.mark_done(cmd2.cmd_id)
