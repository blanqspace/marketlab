from __future__ import annotations

from src.marketlab.orders.schema import OrderTicket
from src.marketlab.orders import store
from src.marketlab.control_menu import _parse_selector


def test_resolve_order_by_token_and_index():
    t = OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None, ttl_sec=300)
    store.put_ticket(t)
    pending = store.get_pending(limit=10)
    assert pending
    tok = pending[0]["token"]
    rec = store.resolve_order_by_token(tok)
    assert rec["id"] == t.id
    rec2 = store.resolve_order(1)
    assert rec2["id"] == rec["id"]


def test_control_menu_parse_selector():
    assert _parse_selector("1") == 1
    assert _parse_selector("ABC7QK") == "ABC7QK"

