from __future__ import annotations

import importlib


def _reload_settings():
    import src.marketlab.settings as s
    importlib.reload(s)
    return s


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("IPC_DB", "runtime/test_ctl.db")
    monkeypatch.setenv("TELEGRAM_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_MOCK", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:abcxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("TG_CHAT_CONTROL", "-100555")
    monkeypatch.setenv("TG_ALLOWLIST", "1,2, 3")
    monkeypatch.setenv("EVENTS_REFRESH_SEC", "9")
    monkeypatch.setenv("KPIS_REFRESH_SEC", "19")
    s = _reload_settings()

    app = s.get_settings()
    assert app.ipc_db == "runtime/test_ctl.db"
    assert app.telegram.enabled is True
    assert app.telegram.mock is True
    assert app.telegram.bot_token is not None
    assert app.telegram.bot_token.get_secret_value().startswith("123456:")
    assert int(app.telegram.chat_control or 0) == -100555
    assert app.telegram.allowlist == [1, 2, 3]
    assert int(app.events_refresh_sec) in (9,)
    assert int(app.kpis_refresh_sec) in (19,)

