from __future__ import annotations
from pathlib import Path
import json, threading, time
from .schema import OrderTicket, ORDER_STATES

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
    idx[t.id] = t.to_dict()
    save_index(idx)
    append_event({"event":"order.put","ticket":t.to_dict(),"ts":time.time()})

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
