from __future__ import annotations

import importlib
import os


def _reload_settings():
    import src.marketlab.settings as s
    importlib.reload(s)
    return s


def test_poller_requires_token(monkeypatch):
    # Enabled, real mode, missing token -> non-zero
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_MOCK", "0")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TG_CHAT_CONTROL", "-100123")
    _reload_settings()

    import tools.tg_poller as poller
    importlib.reload(poller)
    rc = poller.main(once=True)
    assert rc != 0


def test_poller_starts_with_complete_env(monkeypatch):
    # Enabled, real mode, complete env -> zero
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_MOCK", "0")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abcxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("TG_CHAT_CONTROL", "-100123")
    _reload_settings()

    # monkeypatch network to avoid real calls
    import tools.tg_poller as poller
    importlib.reload(poller)

    class _R:
        def __init__(self, code=200, body=None, text=""):
            self.status_code = code
            self._body = body or {"ok": True}
            self.ok = 200 <= code < 300
            self.text = text or "{}"

        def json(self):
            return self._body

    def fake_get(url, params=None, timeout=5):
        return _R(200, {"ok": True, "result": {"id": 1}})

    def fake_post(url, json=None, timeout=5):
        return _R(200, {"ok": True})

    poller.requests.get = fake_get  # type: ignore
    poller.requests.post = fake_post  # type: ignore

    rc = poller.main(once=True)
    assert rc == 0

