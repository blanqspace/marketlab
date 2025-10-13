from __future__ import annotations

from datetime import timedelta
from marketlab.ipc import bus
from marketlab.utils.timefmt import fmt_mm_ss


def test_set_get_state_roundtrip(tmp_path):
    db = str(tmp_path / "ctl.db")
    import os
    os.environ[bus.DB_ENV] = db
    bus.bus_init()

    # ibkr keys
    bus.set_state("ibkr.connected", "1")
    bus.set_state("ibkr.client_id", "7")
    bus.set_state("ibkr.host", "127.0.0.1")
    bus.set_state("ibkr.port", "4002")
    assert bus.get_state("ibkr.connected", "0") == "1"

    # tg keys
    bus.set_state("tg.enabled", "1")
    bus.set_state("tg.mock", "0")
    bus.set_state("tg.bot_username", "marketlab_bot")
    bus.set_state("tg.chat_control", "123")
    bus.set_state("tg.allowlist_count", "2")
    assert bus.get_state("tg.bot_username", "") == "marketlab_bot"


def test_fmt_mm_ss():
    assert fmt_mm_ss(timedelta(seconds=61)) == "01:01"
    assert fmt_mm_ss(timedelta(seconds=0)) == "00:00"
