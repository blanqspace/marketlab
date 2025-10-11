from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from src.marketlab.ipc import bus
from src.marketlab.orders import store as orders
from src.marketlab.settings import get_settings
from src.marketlab.core.timefmt import iso_utc


@dataclass
class WorkerConfig:
    two_man_rule: bool
    confirm_strict: bool
    ttl_seconds: int


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip() in ("1", "true", "TRUE", "yes", "on")


def load_config() -> WorkerConfig:
    # TTL for two-man approval window: TODO make configurable via ENV in future
    ttl = int(os.getenv("ORDERS_TTL_SECONDS", "300"))
    return WorkerConfig(
        two_man_rule=_env_bool("ORDERS_TWO_MAN_RULE", True),
        confirm_strict=_env_bool("CONFIRM_STRICT", True),
        ttl_seconds=ttl,
    )


class Worker:
    """Simple command worker that consumes NEW commands from the bus.

    Policies:
    - Two-man-rule for order confirmations: requires two distinct sources (e.g. telegram and cli).
      This is tracked in-memory for now. TODO: persist approvals for resilience across restarts.
    - TTL applies to approval window. TODO: enforce expiry and emit timeout events.
    - Retries and Dedupe are postponed. TODO markers are in bus layer already.
    """

    def __init__(self, cfg: WorkerConfig | None = None) -> None:
        self.cfg = cfg or load_config()
        # approvals[(cmd, order_id)] -> (first_source, ts)
        self._approvals: Dict[Tuple[str, str], Tuple[str, float]] = {}

    def process_one(self) -> bool:
        cmd = bus.next_new()
        if not cmd:
            return False
        try:
            handled = self._handle(cmd.cmd, cmd.args or {}, cmd.source or "?")
            bus.mark_done(cmd.cmd_id)
            return handled
        except Exception as e:  # pragma: no cover
            bus.mark_error(cmd.cmd_id, str(e))
            return False

    def process_available(self, max_items: int | None = None) -> int:
        """Drain available NEW commands, applying worker policies.

        Returns number of processed items.
        """
        n = 0
        while True:
            if max_items is not None and n >= max_items:
                break
            if not self.process_one():
                break
            n += 1
        return n

    # --- command handlers ---
    def _handle(self, name: str, args: dict[str, Any], source: str) -> bool:
        match name:
            case "state.pause":
                # persist lowercase state for dashboard header stability
                try:
                    bus.set_state("state", "paused")
                except Exception:
                    pass
                # keep legacy uppercase for events (tests/backcompat)
                bus.emit("ok", "state.changed", state="PAUSED", source=source)
                return True
            case "state.resume":
                try:
                    bus.set_state("state", "running")
                except Exception:
                    pass
                bus.emit("ok", "state.changed", state="RUN", source=source)
                return True
            case "state.stop":
                bus.emit("ok", "state.changed", state="STOP", source=source)
                return True
            case "orders.confirm":
                return self._orders_confirm(args, source)
            case "orders.reject":
                oid, tok = self._resolve_id_and_token(args)
                if not oid:
                    bus.emit("error", "orders.reject.failed", reason="missing id", source=source)
                    return False
                bus.emit("ok", "orders.reject.ok", token=tok, source=source)
                return True
            case "orders.confirm_all":
                bus.emit("ok", "orders.confirm_all", source=source)
                return True
            case "mode.switch":
                target = args.get("target")
                try:
                    if target:
                        bus.set_state("mode", str(target))
                except Exception:
                    pass
                bus.emit("info", "mode.enter", mode=target, source=source, args=args)
                return True
            case _:
                bus.emit("warn", "unknown.cmd", cmd=name, source=source, args=args)
                return False

    def _orders_confirm(self, args: dict[str, Any], source: str) -> bool:
        oid, tok = self._resolve_id_and_token(args)
        if not oid:
            bus.emit("error", "orders.confirm.failed", reason="missing id", source=source)
            return False
        if self.cfg.two_man_rule:
            key = ("orders.confirm", oid)
            now = time.time()
            first = self._approvals.get(key)
            if not first:
                # record first approval
                self._approvals[key] = (source, now)
                bus.emit("warn", "orders.confirm.pending", token=tok, source=source)
                return True
            first_source, ts = first
            if source == first_source:
                # same source repeated
                bus.emit("warn", "orders.confirm.pending", token=tok, source=source, note="same_source")
                return True
            # second approval
            if now - ts <= self.cfg.ttl_seconds:
                bus.emit("ok", "orders.confirm.ok", token=tok, sources=[first_source, source])
                # clear approval
                self._approvals.pop(key, None)
                return True
            # expired
            self._approvals.pop(key, None)
            bus.emit("warn", "orders.confirm.expired", token=tok, source=source)
            # record new first
            self._approvals[key] = (source, now)
            return True
        # no two-man rule
        bus.emit("ok", "orders.confirm.ok", token=tok, source=source)
        return True

    def _resolve_id_and_token(self, args: dict[str, Any]) -> tuple[str, str | None]:
        # Prefer explicit token, then selector, then id
        if "token" in args and args.get("token"):
            try:
                rec = orders.resolve_order_by_token(str(args.get("token")))
                return str(rec.get("id")), rec.get("token")
            except Exception:
                return "", None
        sel = args.get("selector") or args.get("id")
        if sel is not None:
            try:
                rec = orders.resolve_order(sel)
                return str(rec.get("id")), rec.get("token")
            except Exception:
                return (str(sel), None) if args.get("id") else ("", None)
        return "", None

    def _token_of(self, oid: str) -> str | None:
        try:
            rec = orders.get_ticket(str(oid))
            return rec.get("token") if rec else None
        except Exception:
            return None


def run_forever(poll_interval: float = 0.5) -> None:  # pragma: no cover
    # ensure a unified DB path from settings
    s = get_settings()
    os.environ[bus.DB_ENV] = s.ipc_db
    bus.bus_init()
    # Log startup and persist app_state for dashboard uptime/metadata
    try:
        pid = os.getpid()
    except Exception:
        pid = -1
    start_ts = int(time.time())
    try:
        bus.set_state("worker_start_ts", iso_utc())
        bus.set_state("state", "running")
    except Exception:
        pass
    bus.emit("info", "worker.start", ipc_db=s.ipc_db, pid=pid, start_ts=start_ts)
    # Optional: dry IBKR connectivity check
    try:
        if bool(getattr(getattr(s, "ibkr", object()), "enabled", False)):
            from src.marketlab.data.adapters import IBKRAdapter
            try:
                a = IBKRAdapter()
                a.connect(getattr(s.ibkr, "host", "127.0.0.1"), int(getattr(s.ibkr, "port", 4002)), int(getattr(s.ibkr, "client_id", 7)), timeout_sec=3)
                a.disconnect()
            except Exception:
                pass
    except Exception:
        pass
    w = Worker()
    while True:
        processed = w.process_available()
        if processed == 0:
            time.sleep(poll_interval)
