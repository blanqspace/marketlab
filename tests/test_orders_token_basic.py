from __future__ import annotations

from marketlab.orders.store import new_token, assign_missing_tokens, load_index, save_index


def test_new_token_charset_and_uniqueness():
    existing = {"ABC123", "XYZ999"}
    tok = new_token(existing, 6)
    assert len(tok) == 6
    for ch in tok:
        assert ch in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    assert tok.upper() not in {x.upper() for x in existing}


def test_assign_missing_tokens_backfills(tmp_path, monkeypatch):
    # simulate store index with missing tokens
    from marketlab.orders import store
    monkeypatch.setenv("ENV_MODE", "TEST")
    store._ensure()
    idx = {}
    idx["id1"] = {
        "id": "id1",
        "symbol": "AAPL",
        "side": "BUY",
        "qty": 1.0,
        "type": "MARKET",
        "state": "PENDING",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    idx["id2"] = {
        "id": "id2",
        "symbol": "MSFT",
        "side": "SELL",
        "qty": 1.0,
        "type": "MARKET",
        "state": "PENDING",
        "created_at": "2024-01-01T00:00:00+00:00",
        "token": "ABCDEF",
    }
    save_index(idx)
    n = assign_missing_tokens()
    assert n == 1
    idx2 = load_index()
    assert idx2["id1"].get("token")
    assert idx2["id2"].get("token") == "ABCDEF"

