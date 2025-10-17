from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("runtime/ctl.db")
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 0.3


class DatabaseUnavailableError(Exception):
    """Raised when the dashboard database cannot be opened in read-only mode."""


@dataclass
class HeaderData:
    mode: str
    state: str
    uptime: str
    queue_depth: int
    events_per_min: float
    last_event_age: int | None


@dataclass
class ConnectionStatus:
    name: str
    status: str
    detail: str
    age_seconds: int | None


@dataclass
class OrderRow:
    token: str
    status: str
    age_seconds: int | None
    sources: str
    message: str


@dataclass
class EventRow:
    id: int
    ts: int
    level: str
    message: str
    fields: dict[str, Any]


@dataclass
class Snapshot:
    header: HeaderData
    kpis: dict[str, Any]
    connections: list[ConnectionStatus]
    orders: list[OrderRow]
    events: list[EventRow]
    last_event_id: int


@dataclass
class EventBatch:
    events: list[EventRow]
    last_event_id: int


def _candidate_bases() -> list[Path]:
    bases: list[Path] = []
    for env_var in ("MARKETLAB_ROOT", "MARKETLAB_HOME"):
        value = os.environ.get(env_var)
        if value:
            try:
                bases.append(Path(value).expanduser())
            except Exception:
                continue
    module_path = Path(__file__).resolve()
    bases.extend(reversed(module_path.parents))
    return bases


def _ensure_path(db_path: str | Path | None) -> Path:
    raw = Path(db_path or DEFAULT_DB).expanduser()
    if raw.is_absolute():
        return raw

    candidate = (Path.cwd() / raw).resolve()
    if candidate.exists() or candidate.parent.exists():
        return candidate

    default_norm = DEFAULT_DB.as_posix().lstrip("./")
    raw_norm = raw.as_posix().lstrip("./")
    if raw_norm != default_norm:
        return candidate

    for base in _candidate_bases():
        try:
            resolved = (base / raw).resolve()
        except Exception:
            continue
        parent = resolved.parent
        if resolved.exists() or parent.exists():
            return resolved

    return candidate


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the SQLite database in read-only mode with retries."""
    path = _ensure_path(db_path)
    conn: sqlite3.Connection | None = None
    last_exc: Exception | None = None

    for _ in range(MAX_RETRIES):
        try:
            conn = sqlite3.connect(
                f"file:{path}?mode=ro",
                uri=True,
                timeout=1.0,
                check_same_thread=False,
            )
            break
        except sqlite3.OperationalError as exc:
            last_exc = exc
            time.sleep(RETRY_BACKOFF_SEC)
    if conn is None:
        msg = f"unable to open database at {path}"
        raise DatabaseUnavailableError(msg) from last_exc

    conn.row_factory = sqlite3.Row
    for pragma in (
        "PRAGMA journal_mode=WAL;",
        "PRAGMA busy_timeout=3000;",
        "PRAGMA synchronous=NORMAL;",
        "PRAGMA temp_store=MEMORY;",
    ):
        try:
            conn.execute(pragma)
        except sqlite3.OperationalError:
            continue
    return conn


def read_snapshot(
    db_path: str | Path | None = None,
    *,
    event_limit: int = 200,
    order_limit: int = 20,
) -> Snapshot:
    """Return a full dashboard snapshot."""
    with closing(get_conn(db_path)) as conn:
        kpis = read_kpis(conn)
        header = _build_header(kpis)
        connections = read_conn_status(conn)
        orders = read_orders_top(conn, order_limit)
        events = read_events(conn, event_limit)
        last_event_id = events[-1].id if events else 0
    return Snapshot(
        header=header,
        kpis=kpis,
        connections=connections,
        orders=orders,
        events=events,
        last_event_id=last_event_id,
    )


def stream_new_events(
    db_path: str | Path | None,
    after_event_id: int,
    *,
    limit: int = 200,
) -> EventBatch:
    """Return events newer than after_event_id."""
    with closing(get_conn(db_path)) as conn:
        rows = _query(
            conn,
            (
                "SELECT id, ts, level, message, fields "
                "FROM events WHERE id > ? ORDER BY id ASC LIMIT ?"
            ),
            (int(after_event_id), int(limit)),
            swallow_no_table=True,
            default=[],
        )
    events = [_row_to_event(row) for row in rows]
    last_id = events[-1].id if events else after_event_id
    return EventBatch(events=events, last_event_id=last_id)


def read_kpis(conn: sqlite3.Connection) -> dict[str, Any]:
    """Fetch KPI metrics, falling back to derived aggregates."""
    rows = _query(
        conn,
        "SELECT key, value FROM kpis",
        swallow_no_table=True,
        default=[],
    )
    if rows:
        data: dict[str, Any] = {}
        for row in rows:
            data[str(row["key"])] = _coerce_value(row["value"])
        _ensure_standard_metrics(conn, data)
        return data

    return _derived_kpis(conn)


def read_conn_status(conn: sqlite3.Connection) -> list[ConnectionStatus]:
    entries: list[ConnectionStatus] = []
    for prefix, friendly in (("ibkr", "IBKR"), ("telegram", "Telegram")):
        row = _query(
            conn,
            "SELECT ts, level, message FROM events WHERE message LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}%",),
            swallow_no_table=True,
            fetch_one=True,
        )
        status, detail, age = "unknown", "n/a", None
        if row:
            message = str(row["message"])
            mapping = {
                f"{prefix}.connected": ("ok", "connected"),
                f"{prefix}.ready": ("ok", "ready"),
                f"{prefix}.disconnected": ("error", "disconnected"),
                f"{prefix}.warn": ("warn", "warning"),
                f"{prefix}.error": ("error", "error"),
            }
            status, detail = mapping.get(message, ("info", message.split(".")[-1]))
            if row["ts"] is not None:
                age = max(0, int(time.time()) - int(row["ts"]))
        entries.append(ConnectionStatus(friendly, status, detail, age))
    return entries


def read_orders_top(conn: sqlite3.Connection, limit: int = 20) -> list[OrderRow]:
    rows = _query(
        conn,
        (
            "SELECT id, ts, message, fields "
            "FROM events WHERE message LIKE 'orders.%' ORDER BY id DESC LIMIT ?"
        ),
        (max(20, int(limit) * 4),),
        swallow_no_table=True,
        default=[],
    )
    snapshots: dict[str, OrderRow] = {}
    now = int(time.time())
    for row in rows:
        fields = _parse_fields(row["fields"])
        token = str(fields.get("token") or fields.get("id") or row["id"])
        status_map = {
            "orders.confirm.pending": "pending",
            "orders.confirm.ok": "confirmed",
            "orders.reject.ok": "rejected",
            "orders.reject.failed": "failed",
            "orders.confirm.expired": "expired",
        }
        message = str(row["message"])
        status = status_map.get(message, message.split(".")[-1])
        sources = fields.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        sources_txt = ", ".join(str(s) for s in sources if str(s).strip()) or "-"
        ts = int(row["ts"]) if row["ts"] is not None else 0
        age_seconds = max(0, now - ts) if ts else None
        if token in snapshots:
            continue
        snapshots[token] = OrderRow(
            token=token,
            status=status,
            age_seconds=age_seconds,
            sources=sources_txt,
            message=message,
        )
        if len(snapshots) >= limit:
            break
    ordered = sorted(snapshots.values(), key=lambda item: item.age_seconds or 0)
    return ordered[:limit]


def read_events(conn: sqlite3.Connection, limit: int = 200) -> list[EventRow]:
    rows = _query(
        conn,
        "SELECT id, ts, level, message, fields FROM events ORDER BY id DESC LIMIT ?",
        (int(max(1, limit)),),
        swallow_no_table=True,
        default=[],
    )
    events = [_row_to_event(row) for row in rows]
    events.reverse()
    return events


def _row_to_event(row: sqlite3.Row) -> EventRow:
    return EventRow(
        id=int(row["id"]),
        ts=int(row["ts"]) if row["ts"] is not None else 0,
        level=str(row["level"]),
        message=str(row["message"]),
        fields=_parse_fields(row["fields"]),
    )


def _build_header(kpis: dict[str, Any]) -> HeaderData:
    last_age_value = kpis.get("last_event_age")
    if isinstance(last_age_value, (int, float)):
        last_age = int(last_age_value)
    else:
        last_age = None

    return HeaderData(
        mode=str(kpis.get("mode", "-")),
        state=str(kpis.get("state", "-")),
        uptime=str(kpis.get("uptime", "--:--")),
        queue_depth=int(kpis.get("queue_depth", 0) or 0),
        events_per_min=float(kpis.get("events_per_min", 0.0) or 0.0),
        last_event_age=last_age,
    )


def _derived_kpis(conn: sqlite3.Connection) -> dict[str, Any]:
    now = int(time.time())
    state_map = _read_app_state(conn)
    mode = state_map.get("mode", {}).get("value", "-")
    state = state_map.get("state", {}).get("value", "-")
    uptime = _format_uptime(state_map.get("worker_start_ts", {}).get("value"))
    queue_depth = _query(
        conn,
        "SELECT COUNT(1) AS c FROM commands WHERE status='NEW'",
        fetch_one=True,
        swallow_no_table=True,
        default={"c": 0},
    )["c"]

    last_60 = now - 60
    events_last_min = _query(
        conn,
        "SELECT COUNT(1) AS c FROM events WHERE ts >= ?",
        (last_60,),
        fetch_one=True,
        swallow_no_table=True,
        default={"c": 0},
    )["c"]
    last_event_row = _query(
        conn,
        "SELECT MAX(ts) AS ts FROM events",
        fetch_one=True,
        swallow_no_table=True,
        default={"ts": None},
    )
    last_event_age = None
    if last_event_row and last_event_row.get("ts") is not None:
        last_event_age = max(0, now - int(last_event_row["ts"]))

    return {
        "mode": mode,
        "state": state,
        "uptime": uptime,
        "queue_depth": int(queue_depth or 0),
        "events_per_min": float(events_last_min),
        "last_event_age": last_event_age,
    }


def _ensure_standard_metrics(conn: sqlite3.Connection, kpis: dict[str, Any]) -> None:
    derived = _derived_kpis(conn)
    for key, value in derived.items():
        kpis.setdefault(key, value)


def _format_uptime(raw_value: Any) -> str:
    if not raw_value:
        return "--:--"
    try:
        start = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        seconds = int(delta.total_seconds())
    except Exception:
        return "--:--"
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _read_app_state(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = _query(
        conn,
        "SELECT key, value, updated_at FROM app_state",
        swallow_no_table=True,
        default=[],
    )
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result[str(row["key"])] = {
            "value": str(row["value"]),
            "updated_at": str(row["updated_at"]),
        }
    return result


def _query(  # noqa: PLR0913
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] | None = None,
    *,
    fetch_one: bool = False,
    swallow_no_table: bool = False,
    default: Any = None,
) -> Any:
    params = params or ()
    for attempt in range(MAX_RETRIES):
        try:
            cur = conn.execute(sql, params)
            if fetch_one:
                row = cur.fetchone()
                if row is None:
                    return default
                return dict(row)
            return cur.fetchall()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "no such table" in message or "no such column" in message:
                if swallow_no_table:
                    return default
                raise
            if "database is locked" in message or "busy" in message:
                if attempt == MAX_RETRIES - 1:
                    return default
                time.sleep(RETRY_BACKOFF_SEC)
                continue
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BACKOFF_SEC)
    return default


def _parse_fields(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _coerce_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    for caster in (int, float):
        try:
            return caster(text)
        except ValueError:
            continue
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text
