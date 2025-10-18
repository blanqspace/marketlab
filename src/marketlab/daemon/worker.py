from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from marketlab.bootstrap.env import load_env
from marketlab.core.control_policy import (
    ControlPolicy,
    approval_window,
    approvals_required,
    command_target,
    policy_for,
)
from marketlab.core.timefmt import iso_utc
from marketlab.ipc import bus
from marketlab.orders import store as orders
from marketlab.settings import get_settings


@dataclass
class WorkerConfig:
    two_man_rule: bool
    confirm_strict: bool
    ttl_seconds: int


def load_config() -> WorkerConfig:
    """Load worker config from App settings (no direct OS env access)."""
    s = get_settings()
    return WorkerConfig(
        two_man_rule=bool(getattr(s, "orders_two_man_rule", True)),
        confirm_strict=bool(getattr(s, "confirm_strict", True)),
        ttl_seconds=int(getattr(s, "orders_ttl_seconds", 300)),
    )


class Worker:
    """Simple command worker that consumes NEW commands from the bus.

    Policies:
    - Policy-driven approvals: applies central risk matrix (two-man rule for HIGH risk) and
      persists pending approvals in the bus database.
    - TTL windows expire automatically and emit approval events for observability.
    - Command retries/backoff handled at bus layer; worker focuses on execution and safety checks.
    """

    BREAKER_THRESHOLD = 5
    BREAKER_WINDOW = 60

    def __init__(self, cfg: WorkerConfig | None = None) -> None:
        self.cfg = cfg or load_config()
        self._last_prune: float = 0.0
        self._error_times: deque[int] = deque()
        self._breaker_tripped: bool = False
        try:
            bus.set_state("breaker.state", "ok")
        except Exception:
            pass

    def process_one(self) -> bool:
        cmd = bus.next_new()
        if not cmd:
            self._expire_approvals()
            return False
        self._expire_approvals()
        args = cmd.args or {}
        source = cmd.source or "?"
        policy = policy_for(cmd.cmd)
        target = self._target_for(cmd.cmd, args)
        try:
            allowed, approvers = self._enforce_policy(cmd, target, policy)
            if not allowed:
                bus.mark_done(cmd.cmd_id)
                return True
            handled = self._execute(cmd.cmd, args, source, approvers)
            bus.mark_done(cmd.cmd_id)
            return handled
        except Exception as e:  # pragma: no cover
            bus.mark_error(cmd.cmd_id, str(e))
            self._record_error(cmd, e)
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
    def _execute(
        self,
        name: str,
        args: dict[str, Any],
        source: str,
        approvers: list[str] | None = None,
    ) -> bool:
        match name:
            case "state.pause":
                self._apply_pause_state()
                return True
            case "state.resume":
                self._apply_resume_state()
                self._reset_breaker()
                return True
            case "state.stop":
                bus.emit("ok", "state.changed", state="STOP", source=source)
                return True
            case "stop.now":
                return self._stop_now(source, approvers)
            case "orders.confirm":
                return self._orders_confirm(args, source, approvers)
            case "orders.reject":
                oid, tok = self._resolve_id_and_token(args)
                if not oid:
                    bus.emit("error", "orders.reject.failed", reason="missing id", source=source)
                    return False
                # include sources list for clarity
                srcs = self._sources_with_fallback(source, approvers)
                bus.emit("ok", "orders.reject.ok", token=tok, sources=srcs)
                return True
            case "orders.confirm_all":
                srcs = self._sources_with_fallback(source, approvers)
                bus.emit("ok", "orders.confirm_all", source=source, approvers=srcs)
                return True
            case "mode.switch":
                target = args.get("target")
                try:
                    if target:
                        bus.set_state("mode", str(target))
                except Exception:
                    pass
                # emit mode enter info; keep payload minimal
                bus.emit("info", "mode.enter", mode=target)
                return True
            case _:
                bus.emit("warn", "unknown.cmd", cmd=name, source=source, args=args)
                return False

    def _orders_confirm(
        self,
        args: dict[str, Any],
        source: str,
        approvers: list[str] | None,
    ) -> bool:
        oid, tok = self._resolve_id_and_token(args)
        if not oid:
            bus.emit("error", "orders.confirm.failed", reason="missing id", source=source)
            return False
        srcs = self._sources_with_fallback(source, approvers)
        bus.emit("ok", "orders.confirm.ok", token=tok, sources=srcs)
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

    def _sources_with_fallback(self, source: str, approvers: list[str] | None) -> list[str]:
        candidates = list(approvers or [])
        if source:
            candidates.append(source)
        cleaned = sorted({s for s in candidates if s})
        return cleaned

    def _apply_pause_state(self) -> None:
        try:
            bus.set_state("state", "paused")
        except Exception:
            pass
        bus.emit("ok", "state.changed", state="PAUSED")

    def _apply_resume_state(self) -> None:
        try:
            bus.set_state("state", "running")
        except Exception:
            pass
        bus.emit("ok", "state.changed", state="RUN")

    def _stop_now(self, source: str, approvers: list[str] | None) -> bool:
        self._apply_pause_state()
        canceled = self._cancel_pending_orders()
        sources = self._sources_with_fallback(source, approvers)
        self._breaker_tripped = True
        self._error_times.clear()
        try:
            bus.set_state("breaker.state", "killswitch")
        except Exception:
            pass
        bus.emit(
            "error",
            "stop.now",
            sources=sources,
            canceled=canceled,
        )
        return True

    def _cancel_pending_orders(self) -> int:
        count = 0
        for state in ("PENDING", "CONFIRMED_TG"):
            for rec in orders.list_tickets(state):
                try:
                    orders.set_state(rec.get("id"), "CANCELED")
                    count += 1
                except Exception:
                    continue
        return count

    def _record_error(self, command: bus.Command, exc: Exception) -> None:
        now = int(time.time())
        self._error_times.append(now)
        window_start = now - self.BREAKER_WINDOW
        while self._error_times and self._error_times[0] < window_start:
            self._error_times.popleft()
        if self._breaker_tripped:
            return
        if len(self._error_times) >= self.BREAKER_THRESHOLD:
            self._trip_breaker(command, len(self._error_times))

    def _trip_breaker(self, command: bus.Command, count: int) -> None:
        if self._breaker_tripped:
            return
        self._breaker_tripped = True
        self._apply_pause_state()
        try:
            bus.set_state("breaker.state", "tripped")
        except Exception:
            pass
        bus.emit(
            "error",
            "breaker.tripped",
            cmd=command.cmd,
            cmd_id=command.cmd_id,
            risk=command.risk_level,
            count=count,
            window=self.BREAKER_WINDOW,
        )

    def _reset_breaker(self) -> None:
        if not self._breaker_tripped and not self._error_times:
            return
        self._breaker_tripped = False
        self._error_times.clear()
        try:
            bus.set_state("breaker.state", "ok")
        except Exception:
            pass
        bus.emit("info", "breaker.reset")

    def _target_for(self, cmd: str, args: dict[str, Any]) -> str:
        target = command_target(cmd, args)
        if cmd == "stop.now":
            return "stop"
        return target

    def _approval_id(self, command: bus.Command, target: str) -> str:
        if approvals_required(command.cmd) > 1:
            base = target or command.cmd_id
            return f"{command.cmd}:{base}"
        if command.request_id:
            return command.request_id
        base = target or command.cmd_id
        return f"{command.cmd}:{base}"

    def _enforce_policy(
        self,
        command: bus.Command,
        target: str,
        policy: ControlPolicy,
    ) -> tuple[bool, list[str]]:
        source = command.source or "?"
        required = max(1, approvals_required(command.cmd))
        if not self.cfg.two_man_rule or required <= 1:
            return True, self._sources_with_fallback(source, None)

        now = int(time.time())
        window = max(5, approval_window(command.cmd))
        approval_id = self._approval_id(command, target)
        record = bus.get_approval(approval_id)

        if record and record["expires_at"] <= now:
            bus.delete_approval(approval_id)
            bus.emit(
                "warn",
                "approval.expired",
                approval_id=approval_id,
                cmd=command.cmd,
                target=target,
                risk=policy.risk,
            )
            if command.cmd == "orders.confirm":
                bus.emit("warn", "orders.confirm.expired", token=target)
            record = None

        entry = {
            "source": source,
            "actor_id": command.actor_id,
            "ts": now,
            "cmd_id": command.cmd_id,
        }
        if command.request_id:
            entry["request_id"] = command.request_id

        if record is None:
            requested_at = command.created_at or now
            record = {
                "approval_id": approval_id,
                "cmd": command.cmd,
                "target": target,
                "risk_level": policy.risk,
                "required": required,
                "approvals": [entry],
                "requested_at": requested_at,
                "expires_at": requested_at + window,
                "last_update": now,
            }
            bus.put_approval(record)
            sources = self._sources_with_fallback(source, None)
            bus.emit(
                "warn",
                "approval.pending",
                approval_id=approval_id,
                cmd=command.cmd,
                target=target,
                risk=policy.risk,
                approvals=len(sources),
                required=required,
                sources=sources,
            )
            if command.cmd == "orders.confirm":
                bus.emit("warn", "orders.confirm.pending", token=target, sources=sources)
            return (False, sources)

        sources = [a.get("source") for a in record.get("approvals", []) if a.get("source")]
        unique_sources = set(sources)
        if source in unique_sources:
            record["last_update"] = now
            bus.put_approval(record)
            bus.emit(
                "warn",
                "approval.pending",
                approval_id=approval_id,
                cmd=command.cmd,
                target=target,
                risk=policy.risk,
                approvals=len(unique_sources),
                required=required,
                sources=sorted(unique_sources),
                note="duplicate_source",
            )
            if command.cmd == "orders.confirm":
                bus.emit(
                    "warn",
                    "orders.confirm.pending",
                    token=target,
                    sources=sorted(unique_sources),
                    note="duplicate_source",
                )
            return False, sorted(unique_sources)

        record.setdefault("approvals", []).append(entry)
        record["last_update"] = now
        bus.put_approval(record)
        unique_sources.add(source)
        sources_list = sorted(unique_sources)

        if len(unique_sources) >= required:
            bus.delete_approval(approval_id)
            bus.emit(
                "ok",
                "approval.fulfilled",
                approval_id=approval_id,
                cmd=command.cmd,
                target=target,
                risk=policy.risk,
                sources=sources_list,
            )
            return True, sources_list

        bus.emit(
            "warn",
            "approval.pending",
            approval_id=approval_id,
            cmd=command.cmd,
            target=target,
            risk=policy.risk,
            approvals=len(unique_sources),
            required=required,
            sources=sources_list,
        )
        if command.cmd == "orders.confirm":
            bus.emit("warn", "orders.confirm.pending", token=target, sources=sources_list)
        return False, sources_list

    def _expire_approvals(self) -> None:
        now = time.time()
        if now - self._last_prune < 5:
            return
        expired = bus.prune_expired_approvals(int(now))
        for rec in expired:
            bus.emit(
                "warn",
                "approval.expired",
                approval_id=rec["approval_id"],
                cmd=rec["cmd"],
                target=rec["target"],
                risk=rec["risk_level"],
            )
            if rec["cmd"] == "orders.confirm":
                bus.emit("warn", "orders.confirm.expired", token=rec["target"])
        self._last_prune = now

    def _token_of(self, oid: str) -> str | None:
        try:
            rec = orders.get_ticket(str(oid))
            return rec.get("token") if rec else None
        except Exception:
            return None


def maybe_connect_ibkr(settings: Any) -> bool:
    """Attempt a short-lived connection to IBKR when enabled."""
    try:
        ibkr_cfg = getattr(settings, "ibkr", None)
        if not ibkr_cfg or not getattr(ibkr_cfg, "enabled", False):
            return False
        from marketlab.data.adapters import IBKRAdapter

        adapter = IBKRAdapter()
        adapter.connect(
            host=getattr(ibkr_cfg, "host", "127.0.0.1"),
            port=int(getattr(ibkr_cfg, "port", 4002)),
            client_id=int(getattr(ibkr_cfg, "client_id", 7)),
            timeout_sec=3,
            readonly=True,
        )
        adapter.disconnect()
        return True
    except Exception:
        return False


def run_forever(poll_interval: float = 0.5) -> None:  # pragma: no cover
    # ensure a unified DB path from settings and mirror env for legacy code
    s = load_env(mirror=True)
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
        maybe_connect_ibkr(s)
    except Exception:
        pass
    w = Worker()
    while True:
        processed = w.process_available()
        if processed == 0:
            time.sleep(poll_interval)
