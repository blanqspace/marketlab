from __future__ import annotations

import importlib
from types import SimpleNamespace


class _DummySecret:
    def __init__(self, v: str):
        self._v = v

    def get_secret_value(self) -> str:
        return self._v


def test_poller_uses_settings_not_osenv(monkeypatch):
    # Set OS env to disabled, but Settings returns enabled=True
    monkeypatch.setenv("TELEGRAM_ENABLED", "0")
    monkeypatch.setenv("TG_CHAT_CONTROL", "-1")

    # Build a minimal AppSettings-like object
    telegram = SimpleNamespace(
        enabled=True,
        mock=True,
        bot_token=_DummySecret("111:abcdxxxxxxxxxxxxxxxxxxxxxx"),
        chat_control=-100777,
        timeout_sec=5,
        debug=False,
        allowlist=[42, 43],
    )
    app = SimpleNamespace(
        env_mode="TEST",
        app_brand="MarketLab",
        ipc_db="runtime/ctl.db",
        events_refresh_sec=5,
        kpis_refresh_sec=15,
        dashboard_warn_only=0,
        telegram=telegram,
    )

    # Monkeypatch settings getter used by bootstrap and poller
    import src.marketlab.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: app, raising=True)

    # Import poller fresh
    import tools.tg_poller as poller
    importlib.reload(poller)

    # Fake network
    class _R:
        def __init__(self, code=200, body=None, text=""):
            self.status_code = code
            self._body = body or {"ok": True}
            self.ok = 200 <= code < 300
            self.text = text or "{}"

        def json(self):
            return self._body

    poller.requests.get = lambda url, params=None, timeout=5: _R(200, {"ok": True, "result": {"id": 1}})  # type: ignore
    poller.requests.post = lambda url, json=None, timeout=5: _R(200, {"ok": True})  # type: ignore

    # Should respect Settings() (enabled=True) and return 0 in once-mode
    rc = poller.main(once=True)
    assert rc == 0

