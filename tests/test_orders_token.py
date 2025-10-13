from __future__ import annotations

import os
from marketlab.orders.schema import OrderTicket
from marketlab.orders import store


def test_generate_token_charset_and_length():
    tok = store.generate_token(6)
    assert len(tok) == 6
    for ch in tok:
        assert ch in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def test_token_uniqueness_and_resolve(tmp_path, monkeypatch):
    # fresh store directory
    base = tmp_path / "orders"
    os.makedirs("runtime/orders", exist_ok=True)
    # create several tickets
    ids = []
    for i in range(10):
        t = OrderTicket.new("AAPL", "BUY", 1 + i, "MARKET", None, None, None, ttl_sec=300)
        store.put_ticket(t)
        ids.append(t.id)
    pending = store.get_pending(limit=20)
    assert len(pending) >= 1
    tokens = [p["token"] for p in pending]
    assert len(tokens) == len(set(tokens))
    # resolve by index
    one = store.resolve_order(1)
    assert one.get("id") in ids
    # resolve by token
    tok = pending[0]["token"]
    via_tok = store.resolve_order(tok)
    assert via_tok.get("id") in ids
    # resolve by id
    via_id = store.resolve_order(ids[0])
    assert via_id.get("id") == ids[0]

