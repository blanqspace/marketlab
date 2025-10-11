from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from tools.tui_dashboard import _ibkr_panel, _tg_panel


def test_ibkr_panel_render(monkeypatch):
    # Mock get_state
    vals = {
        "ibkr.enabled": "1",
        "ibkr.connected": "0",
        "ibkr.host": "127.0.0.1",
        "ibkr.port": "4002",
        "ibkr.client_id": "7",
        "ibkr.market_data_type": "3",
        "ibkr.last_err": "unavailable",
    }
    monkeypatch.setattr("tools.tui_dashboard.get_state", lambda k, d="": vals.get(k, d))
    p = _ibkr_panel()
    assert isinstance(p, Panel)
    con = Console(width=80, record=True)
    con.print(p)
    text = con.export_text()
    assert "IBKR" in text
    assert "enabled: Yes" in text
    assert "connected:" in text
    assert "host:port: 127.0.0.1:4002" in text
    assert "client_id: 7" in text


def test_tg_panel_render(monkeypatch):
    vals = {
        "tg.enabled": "1",
        "tg.mock": "1",
        "tg.bot_username": "botname",
        "tg.chat_control": "123",
        "tg.allowlist_count": "3",
        "tg.last_err": "",
    }
    monkeypatch.setattr("tools.tui_dashboard.get_state", lambda k, d="": vals.get(k, d))
    p = _tg_panel()
    assert isinstance(p, Panel)
    con = Console(width=80, record=True)
    con.print(p)
    text = con.export_text()
    assert "Telegram" in text
    assert "enabled: Yes" in text
    assert "mock: Yes" in text
    assert "bot: botname" in text
    assert "chat: 123" in text
    assert "allowlist: 3" in text
