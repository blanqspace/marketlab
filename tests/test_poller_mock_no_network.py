from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def _mock_settings() -> SimpleNamespace:
    telegram = SimpleNamespace(
        enabled=True,
        mock=True,
        bot_token=SimpleNamespace(get_secret_value=lambda: "123456789:mocktokenmocktokenmock"),
        chat_control=-1,
        timeout_sec=1,
        long_poll_sec=1,
        debug=False,
        allowlist=[],
    )
    return SimpleNamespace(
        telegram=telegram, env_mode="TEST", app_brand="MarketLab", ipc_db="runtime/ctl.db"
    )


def test_poller_mock_mode_skips_http(monkeypatch):
    import marketlab.tools.tg_poller as wrapper

    import tools.tg_poller as poller

    importlib.reload(poller)

    monkeypatch.setattr(poller, "load_env", lambda mirror=True: _mock_settings(), raising=True)
    bus_stub = SimpleNamespace(set_state=lambda *a, **kw: None, emit=lambda *a, **kw: None)
    monkeypatch.setattr(poller, "bus", bus_stub, raising=True)

    def boom(*_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("network call attempted in mock mode")

    monkeypatch.setattr(poller.requests, "get", boom, raising=False)
    monkeypatch.setattr(poller.requests, "post", boom, raising=False)

    rc = wrapper.main(once=True)
    assert rc == 0
