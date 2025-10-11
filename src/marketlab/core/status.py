from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..core.state_manager import STATE
from ..orders.store import counts as order_counts, list_tickets
from ..orders.store import load_index
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
        "mode": st.get("mode", "unknown"),
        "run_state": st.get("state", "unknown"),
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


# --- New KPI helpers for dashboard/supervisor ---

def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def queue_depth(db_path: str) -> int:
    try:
        with _connect(db_path) as con:
            row = con.execute("SELECT COUNT(1) FROM commands WHERE status='NEW'").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def recent_cmd_counts(db_path: str, window_sec: int = 300) -> Dict[str, int]:
    """Counts of commands created within window by status.

    Uses commands.available_at as creation time reference.
    """
    try:
        with _connect(db_path) as con:
            row = con.execute("SELECT strftime('%s','now')").fetchone()
            now = int(row[0]) if row else 0
            since = now - int(max(1, window_sec))
            cur = con.execute(
                "SELECT status, COUNT(1) AS c FROM commands WHERE available_at >= ? GROUP BY status",
                (since,),
            )
            out = {"NEW": 0, "DONE": 0, "ERROR": 0}
            for r in cur.fetchall():
                st = str(r[0])
                if st in out:
                    out[st] = int(r[1])
            return out
    except Exception:
        return {"NEW": 0, "DONE": 0, "ERROR": 0}


def _events_stats(db_path: str, window_sec: int = 300) -> Tuple[float, int]:
    """Return (events_per_min, last_event_age_s)."""
    try:
        with _connect(db_path) as con:
            now = int(con.execute("SELECT strftime('%s','now')").fetchone()[0])
            since = now - int(window_sec)
            row = con.execute("SELECT COUNT(1) FROM events WHERE ts >= ?", (since,)).fetchone()
            cnt = int(row[0]) if row else 0
            per_min = cnt / max(1, (window_sec / 60.0))
            row2 = con.execute("SELECT ts FROM events ORDER BY id DESC LIMIT 1").fetchone()
            if not row2:
                return (0.0, -1)
            last_age = max(0, now - int(row2[0]))
            return (per_min, last_age)
    except Exception:
        return (0.0, -1)


def _orders_counts() -> Dict[str, int]:
    try:
        return order_counts() or {}
    except Exception:
        return {}


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        try:
            # python<3.11 may need this
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None


def orders_summary(db_path: str) -> Dict[str, Any]:
    """Return counts and TTL stats for pending orders plus two-man pending state.

    - counts: pending, confirmed, rejected
    - two_man_pending_count: unique tokens awaiting second approval (based on recent events)
    - avg_ttl_left: average seconds until pending tickets expire (PENDING/CONFIRMED_TG)
    """
    counts = _orders_counts()
    # Average TTL left for pending-like states
    try:
        idx = load_index()
        now = datetime.now(timezone.utc)
        ttl_left: List[float] = []
        for rec in idx.values():
            st = rec.get("state")
            if st in ("PENDING", "CONFIRMED_TG"):
                exp = _parse_iso(str(rec.get("expires_at", "")))
                if exp is not None:
                    ttl_left.append((exp - now).total_seconds())
        avg_ttl = sum(ttl_left) / len(ttl_left) if ttl_left else 0.0
    except Exception:
        avg_ttl = 0.0

    # two-man pending inferred from recent events
    two_man = 0
    try:
        ttl_env = int(os.getenv("ORDERS_TTL_SECONDS", "300"))
        with _connect(db_path) as con:
            now_s = int(con.execute("SELECT strftime('%s','now')").fetchone()[0])
            since = now_s - int(ttl_env)
            cur = con.execute(
                "SELECT json_extract(fields,'$.token') AS tok, MAX(ts) AS ts FROM events WHERE message='orders.confirm.pending' AND ts >= ? GROUP BY tok",
                (since,),
            )
            # count non-null tokens still within TTL window
            tokens = [str(r[0]) for r in cur.fetchall() if r and r[0]]
            two_man = len(tokens)
    except Exception:
        two_man = 0

    return {
        "pending": int(counts.get("PENDING", 0)),
        "confirmed": int(counts.get("CONFIRMED", 0)),
        "rejected": int(counts.get("REJECTED", 0)),
        "two_man_pending_count": two_man,
        "avg_ttl_left": avg_ttl,
    }


def events_tail_agg(db_path: str, n: int = 100) -> List[Dict[str, Any]]:
    """Aggregate last N events by (level, message, fields-signature).

    Returns list of dicts with keys: ts (latest in group), level, message, fields, count.
    """
    try:
        with _connect(db_path) as con:
            cur = con.execute(
                "SELECT ts, level, message, fields FROM events ORDER BY id DESC LIMIT ?",
                (int(max(1, n)),),
            )
            groups: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            for r in cur.fetchall():
                ts = int(r["ts"]) if r["ts"] is not None else 0
                lvl = str(r["level"])
                msg = str(r["message"])
                fields = json.loads(r["fields"]) if r["fields"] else {}
                # signature: stable JSON of fields (sorted)
                try:
                    sig = json.dumps(fields or {}, ensure_ascii=False, sort_keys=True)
                except Exception:
                    sig = "{}"
                key = (lvl, msg, sig)
                g = groups.get(key)
                if not g:
                    groups[key] = {
                        "ts": ts,
                        "level": lvl,
                        "message": msg,
                        "fields": fields or {},
                        "count": 1,
                    }
                else:
                    # keep latest ts and increment count
                    if ts > int(g.get("ts", 0)):
                        g["ts"] = ts
                    g["count"] = int(g.get("count", 1)) + 1
            # Sort by ts desc (latest first)
            out = sorted(groups.values(), key=lambda x: int(x.get("ts", 0)), reverse=True)
            return out
    except Exception:
        return []


def snapshot_kpis(db_path: str) -> Dict[str, Any]:
    """Collect all KPIs needed by dashboard header and KPI panel."""
    # events stats
    per_min, last_age = _events_stats(db_path, window_sec=300)
    # cmd window counts
    cmd_counts = recent_cmd_counts(db_path, window_sec=300)
    # orders summary
    ords = orders_summary(db_path)
    # worker meta from last worker.start
    worker_pid = None
    uptime_s = None
    db_base = os.path.basename(db_path)
    try:
        with _connect(db_path) as con:
            row = con.execute(
                "SELECT ts, fields FROM events WHERE message='worker.start' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                ts = int(row[0])
                fields = json.loads(row[1]) if row[1] else {}
                now = int(con.execute("SELECT strftime('%s','now')").fetchone()[0])
                uptime_s = max(0, now - (int(fields.get("start_ts", ts)) or ts))
                worker_pid = int(fields.get("pid")) if fields.get("pid") is not None else None
    except Exception:
        pass
    return {
        "cmd_counts_5m": cmd_counts,
        "events_per_min": per_min,
        "last_event_age": last_age,
        "orders_summary": ords,
        "two_man_pending_count": ords.get("two_man_pending_count", 0),
        "avg_ttl_left": ords.get("avg_ttl_left", 0.0),
        "db_basename": db_base,
        "worker_pid": worker_pid,
        "uptime_s": uptime_s,
    }

