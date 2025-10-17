from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path
from typing import Any

from ..settings import get_settings
from .schema import ORDER_STATES, OrderTicket

_BASE = Path("runtime/orders")
_LOG = _BASE / "orders.jsonl"
_STATE = _BASE / "state.json"
_LOCK = threading.RLock()

def _ensure():
    _BASE.mkdir(parents=True, exist_ok=True)
    if not _STATE.exists(): _STATE.write_text("{}", encoding="utf-8")

def append_event(event: dict):
    _ensure()
    with _LOCK:
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

def load_index() -> dict:
    _ensure()
    with _LOCK:
        return json.loads(_STATE.read_text(encoding="utf-8") or "{}")

def save_index(idx: dict):
    _ensure()
    with _LOCK:
        _STATE.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

def put_ticket(t: OrderTicket):
    idx = load_index()
    # ensure token present and unique, stable once assigned
    rec = t.to_dict()
    tok_len = int(getattr(get_settings(), "orders_token_len", 6))
    if not rec.get("token"):
        rec["token"] = _next_unique_token(idx, tok_len)
    idx[t.id] = rec
    save_index(idx)
    append_event({"event":"order.put","ticket":rec,"ts":time.time()})

def get_ticket(oid: str) -> dict | None:
    return load_index().get(oid)

def set_state(oid: str, state: str):
    assert state in ORDER_STATES
    idx = load_index()
    if oid in idx:
        idx[oid]["state"] = state
        save_index(idx)
        append_event({"event":"order.state","id":oid,"state":state,"ts":time.time()})

def list_tickets(state: str | None = None) -> list[dict]:
    idx = load_index()
    vals = list(idx.values())
    return [v for v in vals if state is None or v["state"] == state]

def counts() -> dict:
    idx = load_index()
    from collections import Counter
    c = Counter(v["state"] for v in idx.values())
    return dict(c)

def first_by_state(state: str) -> dict | None:
    for t in list_tickets(state):
        return t
    return None


# --- Short Order Token (SOT) utilities ---
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # excludes 0,O,1,I


def generate_token(length: int = 6) -> str:
    """Generate a random short token consisting of A-Z (without O/I) and 2-9.

    Ensures no ambiguous characters for quick voice/keyboard input.
    """
    return "".join(random.choice(_ALPHABET) for _ in range(max(3, int(length))))


def new_token(existing: set[str], length: int = 6) -> str:
    """Generate a unique token not in existing.

    Alphabet: A-Z without O/I, digits 2-9. Case-insensitive uniqueness.
    """
    used = {str(x).upper() for x in (existing or set())}
    curr_len = max(3, int(length))
    attempts = 0
    while True:
        t = generate_token(curr_len)
        if t.upper() not in used:
            return t
        attempts += 1
        if attempts > 500:
            attempts = 0
            curr_len += 1


def _existing_tokens(idx: dict[str, dict]) -> set[str]:
    return {str(v.get("token", "")).upper() for v in (idx or {}).values() if v.get("token")}


def _next_unique_token(idx: dict[str, dict], length: int) -> str:
    used = _existing_tokens(idx)
    return new_token(used, length)


def get_pending(limit: int = 20) -> list[dict[str, Any]]:
    """Return up to `limit` pending orders with lite fields.

    Fields: id, token, symbol, side, qty, type, state, created_at
    """
    rows = []
    for st in ("PENDING", "CONFIRMED_TG"):
        rows.extend(list_tickets(st))
    # sort by created_at desc if available
    def _key(r: dict):
        return r.get("created_at", "")
    rows.sort(key=_key, reverse=True)
    lite = []
    for r in rows[: max(1, int(limit))]:
        lite.append(
            {
                "id": r.get("id"),
                "token": r.get("token"),
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "qty": r.get("qty"),
                "type": r.get("type"),
                "state": r.get("state"),
                "created_at": r.get("created_at"),
            }
        )
    return lite


def resolve_order(selector: str | int) -> dict:
    """Resolve selector to full order dict.

    - int: select 1-based index within current get_pending()
    - str: token match (case-insensitive)
    - else: fallback to full id
    Raises ValueError if not found.
    """
    # int index
    if isinstance(selector, int):
        pend = get_pending()
        if selector < 1 or selector > len(pend):
            raise ValueError("ungültiger Selector")
        oid = pend[selector - 1]["id"]
        rec = get_ticket(str(oid))
        if not rec:
            raise ValueError("ungültiger Selector")
        return rec
    # str token or id
    sel = str(selector).strip()
    if not sel:
        raise ValueError("ungültiger Selector")
    # try token
    needle = sel.upper()
    for r in load_index().values():
        tok = str(r.get("token", "")).upper()
        if tok and tok == needle:
            return r
    # fallback to id
    rec = get_ticket(sel)
    if rec:
        return rec
    raise ValueError("ungültiger Selector")


def resolve_order_by_token(token: str) -> dict:
    """Resolve order strictly by token (case-insensitive)."""
    needle = str(token or "").strip().upper()
    if not needle:
        raise ValueError("ungültiger Selector")
    for r in load_index().values():
        if str(r.get("token", "")).upper() == needle:
            return r
    raise ValueError("ungültiger Selector")


def assign_missing_tokens() -> int:
    """Backfill tokens for orders missing them. Returns number of assignments."""
    idx = load_index()
    used = _existing_tokens(idx)
    changed = 0
    for oid, rec in idx.items():
        if not rec.get("token"):
            rec["token"] = new_token(used, int(getattr(get_settings(), "orders_token_len", 6)))
            used.add(rec["token"].upper())
            changed += 1
    if changed:
        save_index(idx)
    return changed
