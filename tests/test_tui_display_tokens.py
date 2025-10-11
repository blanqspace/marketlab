from __future__ import annotations

from tools.tui_dashboard import render, _orders_panel


def test_dashboard_orders_shows_tok_not_id():
    # Inspect orders panel columns
    pnl = _orders_panel()
    tbl = pnl.renderable  # Panel(Table)
    headers = [str(c.header) for c in tbl.columns]
    assert "Tok" in headers
    assert "ID" not in headers
