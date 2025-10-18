from __future__ import annotations

from types import SimpleNamespace

import pytest

import marketlab.daemon.worker as worker_module


def test_maybe_connect_ibkr_uses_keywords(monkeypatch):
    cfg = SimpleNamespace(
        ibkr=SimpleNamespace(enabled=True, host="ibkr-host", port=4001, client_id=77)
    )

    class DummyAdapter:
        def __init__(self) -> None:
            self.connected = False

        def connect(self, *, host, port, client_id, timeout_sec, readonly=True):  # noqa: ANN001
            assert host == "ibkr-host"
            assert port == 4001
            assert client_id == 77
            assert timeout_sec == 3
            assert readonly is True
            self.connected = True
            return self

        def disconnect(self) -> None:
            assert self.connected

    monkeypatch.setattr("marketlab.data.adapters.IBKRAdapter", DummyAdapter)
    assert worker_module.maybe_connect_ibkr(cfg) is True
