from __future__ import annotations

from typing import Any, Dict

from marketlab.ipc import bus
from marketlab.orders import store as orders
from marketlab.settings import get_settings


def build_main_menu() -> dict:
    """Return Inline-Keyboard JSON for main actions and dynamic order buttons."""

    def btn(text: str, action: str, extra: dict | None = None) -> dict:
        payload: dict[str, Any] = {"action": action}
        if extra:
            payload.update(extra)
        # Telegram expects JSON string; we keep it minimal
        return {"text": text, "callback_data": str(payload).replace("'", '"')}

    rows = [
        [btn("Pause", "pause"), btn("Resume", "resume"), btn("Stop", "stop")],
        [btn("Mode Paper", "mode_paper"), btn("Mode Live", "mode_live")],
    ]
    # Dynamic section: tokens per pending order
    try:
        n_show = getattr(get_settings(), "orders_show_recent", 6)
        pend = orders.get_pending(limit=n_show)
        for r in pend:
            tok = r.get("token", "-")
            sym = r.get("symbol", "-")
            rows.append([
                btn(f"Confirm {tok}", "confirm_token", {"token": tok, "symbol": sym}),
                btn(f"Reject {tok}", "reject_token", {"token": tok, "symbol": sym}),
            ])
    except Exception:
        pass
    return {"inline_keyboard": rows}


def handle_callback(data: dict) -> None:
    """Map callback data dict to bus commands.

    Expected format: {"action": ..., ...}
    Raises ValueError if required data (e.g., id) is missing.
    """
    action = str(data.get("action", "")).strip()
    if not action:
        raise ValueError("missing action")

    if action == "pause":
        bus.enqueue("state.pause", {}, source="telegram")
        return
    if action == "resume":
        bus.enqueue("state.resume", {}, source="telegram")
        return
    if action == "stop":
        bus.enqueue("state.stop", {}, source="telegram")
        return
    if action == "confirm":
        oid = data.get("id")
        if not oid:
            raise ValueError("Bitte ID")
        bus.enqueue("orders.confirm", {"id": str(oid)}, source="telegram")
        return
    if action == "reject":
        oid = data.get("id")
        if not oid:
            raise ValueError("Bitte ID")
        bus.enqueue("orders.reject", {"id": str(oid)}, source="telegram")
        return
    if action == "confirm_token":
        tok = data.get("token")
        if not tok:
            raise ValueError("ungültiger Selector")
        bus.enqueue("orders.confirm", {"token": str(tok)}, source="telegram")
        return
    if action == "reject_token":
        tok = data.get("token")
        if not tok:
            raise ValueError("ungültiger Selector")
        bus.enqueue("orders.reject", {"token": str(tok)}, source="telegram")
        return
    if action == "mode_paper":
        bus.enqueue(
            "mode.switch",
            {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            source="telegram",
        )
        return
    if action == "mode_live":
        bus.enqueue(
            "mode.switch",
            {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            source="telegram",
        )
        return

    raise ValueError(f"unknown action: {action}")
