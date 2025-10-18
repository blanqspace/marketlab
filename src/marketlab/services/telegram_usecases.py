from __future__ import annotations

from typing import Any

from marketlab.ipc import bus
from marketlab.core.control_policy import (
    approval_window,
    approvals_required,
    command_target,
    risk_of_command,
)
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


def _actor_label(actor_id: int | None) -> str:
    return f"tg:{actor_id}" if actor_id is not None else "tg:unknown"


def enqueue_control(cmd: str, args: dict[str, Any], actor_id: int | None) -> str:
    target = command_target(cmd, args)
    if target == cmd:
        base = bus.stable_request_id(cmd, args)
    else:
        base = f"{cmd}:{target}"
    actor = _actor_label(actor_id)
    if approvals_required(cmd) > 1 and actor:
        base = f"{base}:{actor}"
    rid = base
    ttl = max(bus.DEFAULT_TTL, approval_window(cmd) + 30)
    return bus.enqueue(
        cmd,
        args,
        source="telegram",
        ttl_sec=ttl,
        actor_id=actor,
        request_id=rid,
        risk_level=risk_of_command(cmd),
    )


def handle_callback(data: dict, actor_id: int | None = None) -> None:
    """Map callback data dict to bus commands.

    Expected format: {"action": ..., ...}
    Raises ValueError if required data (e.g., id) is missing.
    """
    action = str(data.get("action", "")).strip()
    if not action:
        raise ValueError("missing action")

    if action == "pause":
        enqueue_control("state.pause", {}, actor_id)
        return
    if action == "resume":
        enqueue_control("state.resume", {}, actor_id)
        return
    if action == "stop":
        enqueue_control("stop.now", {}, actor_id)
        return
    if action == "confirm":
        oid = data.get("id")
        if not oid:
            raise ValueError("Bitte ID")
        enqueue_control("orders.confirm", {"id": str(oid)}, actor_id)
        return
    if action == "reject":
        oid = data.get("id")
        if not oid:
            raise ValueError("Bitte ID")
        enqueue_control("orders.reject", {"id": str(oid)}, actor_id)
        return
    if action == "confirm_token":
        tok = data.get("token")
        if not tok:
            raise ValueError("ungültiger Selector")
        enqueue_control("orders.confirm", {"token": str(tok)}, actor_id)
        return
    if action == "reject_token":
        tok = data.get("token")
        if not tok:
            raise ValueError("ungültiger Selector")
        enqueue_control("orders.reject", {"token": str(tok)}, actor_id)
        return
    if action == "mode_paper":
        enqueue_control(
            "mode.switch",
            {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            actor_id,
        )
        return
    if action == "mode_live":
        enqueue_control(
            "mode.switch",
            {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}},
            actor_id,
        )
        return

    raise ValueError(f"unknown action: {action}")
