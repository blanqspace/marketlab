from __future__ import annotations

import time
from typing import Dict, Set

from marketlab.ipc import bus
from marketlab.utils.logging import get_logger

log = get_logger("confirm_worker")


def _prune_expired(seen: Dict[str, Dict[str, object]], ttl_sec: int) -> None:
    if ttl_sec <= 0:
        return
    cutoff = time.time() - ttl_sec
    expired = [token for token, meta in seen.items() if float(meta.get("ts", 0.0)) < cutoff]
    for token in expired:
        seen.pop(token, None)


def run_forever(ttl_sec: int = 300) -> None:
    """Konsumiert commands und emittiert orders.confirm.pending/ok gemäß Two-Man-Rule."""
    seen: Dict[str, Dict[str, object]] = {}
    log.info("confirm_worker listening", extra={"ttl": ttl_sec})
    try:
        while True:
            try:
                _prune_expired(seen, ttl_sec)
                cmd = bus.next_new()
                if not cmd:
                    time.sleep(0.5)
                    continue
                if cmd.cmd != "orders.confirm":
                    bus.mark_done(cmd.cmd_id)
                    continue
                args = cmd.args or {}
                token = args.get("token")
                source = cmd.source or "unknown"
                if not token:
                    log.warning("orders.confirm without token", extra={"cmd_id": cmd.cmd_id})
                    bus.mark_done(cmd.cmd_id)
                    continue
                record = seen.setdefault(token, {"sources": set(), "ts": time.time()})
                sources: Set[str] = record["sources"]  # type: ignore[assignment]
                sources.add(str(source))
                record["ts"] = time.time()
                sources_list = sorted(sources)
                if "cli" in sources and "slack" in sources:
                    bus.emit("info", "orders.confirm.ok", token=token, by=source, sources=sources_list)
                    log.info("emit confirm ok", extra={"token": token, "sources": sources_list})
                    seen.pop(token, None)
                else:
                    bus.emit("debug", "orders.confirm.pending", token=token, sources=sources_list)
                    log.info("emit confirm pending", extra={"token": token, "sources": sources_list})
                bus.mark_done(cmd.cmd_id)
            except Exception as exc:
                log.error("worker error", exc_info=exc)
                time.sleep(0.5)
    except KeyboardInterrupt:
        log.info("confirm_worker stopped via signal")
