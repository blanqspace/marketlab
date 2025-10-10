from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import hashlib, json

ORDER_STATES = {"PENDING","CONFIRMED_TG","CONFIRMED","REJECTED","CANCELED","EXECUTED"}

@dataclass
class OrderTicket:
    id: str
    symbol: str
    side: str            # BUY | SELL
    qty: float
    type: str           # MARKET | LIMIT
    limit: float | None = None
    sl: float | None = None
    tp: float | None = None
    created_at: str = ""
    expires_at: str = ""
    state: str = "PENDING"
    checksum: str = ""

    @staticmethod
    def new(symbol: str, side: str, qty: float, type: str, limit: float | None, sl: float | None, tp: float | None, ttl_sec: int = 120):
        now = datetime.now(timezone.utc)
        oid = uuid4().hex
        data = {
            "id": oid, "symbol": symbol.upper(), "side": side.upper(), "qty": float(qty),
            "type": type.upper(), "limit": float(limit) if limit is not None else None,
            "sl": float(sl) if sl is not None else None, "tp": float(tp) if tp is not None else None,
            "created_at": now.isoformat(), "expires_at": (now + timedelta(seconds=ttl_sec)).isoformat(),
            "state": "PENDING",
        }
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        data["checksum"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return OrderTicket(**data)

    def to_dict(self): return asdict(self)
