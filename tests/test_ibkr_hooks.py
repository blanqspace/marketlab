from __future__ import annotations

import os
import sys
import types

from src.marketlab.ipc import bus
from src.marketlab.data.adapters import IBKRAdapter


def test_ibkr_connect_disconnect_state(monkeypatch, tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()

    # Stub ib_insync.IB
    class _StubIB:
        def connect(self, host, port, clientId, timeout):
            self._ok = True
        def reqMarketDataType(self, t):
            pass
        def disconnect(self):
            pass

    mod = types.SimpleNamespace(IB=_StubIB)
    monkeypatch.setitem(sys.modules, 'ib_insync', mod)  # type: ignore[name-defined]

    a = IBKRAdapter()
    a.connect("127.0.0.1", 4002, client_id=7, timeout_sec=1)
    assert bus.get_state("ibkr.connected", "0") == "1"
    assert bus.get_state("ibkr.client_id", "") == "7"
    a.disconnect()
    assert bus.get_state("ibkr.connected", "1") == "0"
