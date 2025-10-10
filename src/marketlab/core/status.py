from __future__ import annotations
from datetime import datetime, timezone
from ..core.state_manager import STATE
from ..orders.store import counts as order_counts, list_tickets
from ..services.telegram_service import telegram_service

def snapshot() -> dict:
    st = STATE.snapshot() if hasattr(STATE, "snapshot") else {}
    now = datetime.now(timezone.utc).isoformat()
    tg = {
        "enabled": getattr(telegram_service, "_running", False),
        "mock": getattr(telegram_service, "_mock", False),
    }
    orders = order_counts()
    pending = list_tickets("PENDING") + list_tickets("CONFIRMED_TG")
    return {
        "ts": now,
        "mode": st.get("mode","unknown"),
        "run_state": st.get("state","unknown"),
        "processed": st.get("processed", 0),
        "should_stop": st.get("should_stop", False),
        "telegram": tg,
        "orders": {
            "counts": orders,
            "pending_preview": pending[:5],
        },
        "health": {
            "ok": True,  # einfache Heuristik; Health-CLI bewertet detaillierter
        },
    }

