from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_RISK = "LOW"
DEFAULT_TTL = 300

DB_ENV = "IPC_DB"
DEFAULT_DB = "runtime/ctl.db"


def _db_path() -> Path:
    return Path(os.getenv(DB_ENV, DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # Pragmas for WAL and reasonable durability
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def bus_init() -> None:
    with _connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS commands (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cmd_id TEXT UNIQUE,
              cmd TEXT NOT NULL,
              args TEXT NOT NULL,
              source TEXT,
              status TEXT NOT NULL DEFAULT 'NEW',
              dedupe_key TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              available_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
              ttl_sec INTEGER,
              actor_id TEXT,
              request_id TEXT,
              risk_level TEXT NOT NULL DEFAULT 'LOW',
              created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
            """
        )
        _ensure_command_columns(con)
        # Lightweight application state key-value store
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),
              level TEXT NOT NULL,
              message TEXT NOT NULL,
              fields TEXT
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_commands_new ON commands(status, available_at);"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_commands_dedupe ON commands(dedupe_key);"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_commands_request ON commands(request_id) WHERE request_id IS NOT NULL;"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS command_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),
              cmd_id TEXT NOT NULL,
              phase TEXT NOT NULL,
              payload TEXT
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_command_audit_cmd ON command_audit(cmd_id);"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
              approval_id TEXT PRIMARY KEY,
              cmd TEXT NOT NULL,
              target TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              required INTEGER NOT NULL,
              approvals TEXT NOT NULL,
              requested_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              last_update INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_approvals_expires ON approvals(expires_at);"
        )


def _ensure_command_columns(con: sqlite3.Connection) -> None:
    """Add newer metadata columns when migrating an existing DB."""
    try:
        cur = con.execute("PRAGMA table_info(commands)")
    except sqlite3.DatabaseError:
        return
    cols = {row[1] for row in cur.fetchall()}
    if "actor_id" not in cols:
        con.execute("ALTER TABLE commands ADD COLUMN actor_id TEXT;")
    if "request_id" not in cols:
        con.execute("ALTER TABLE commands ADD COLUMN request_id TEXT;")
    if "risk_level" not in cols:
        con.execute(
            "ALTER TABLE commands ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'LOW';"
        )
    if "created_at" not in cols:
        con.execute("ALTER TABLE commands ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0;")


def _now() -> int:
    return int(time.time())


def _ensure_cmd_id(con: sqlite3.Connection) -> str:
    # Generate a sortable command id using epoch and rowid later
    # Here we just return epoch-ns string for uniqueness
    return f"cmd_{int(time.time()*1e9):d}"


def _risk_for(cmd: str) -> str:
    try:
        from marketlab.core.control_policy import risk_of_command
    except Exception:
        return DEFAULT_RISK
    try:
        return str(risk_of_command(cmd)).upper()
    except Exception:
        return DEFAULT_RISK


def enqueue(
    cmd: str,
    args: dict[str, Any],
    source: str,
    ttl_sec: int = DEFAULT_TTL,
    dedupe_key: str | None = None,
    *,
    actor_id: str | None = None,
    request_id: str | None = None,
    risk_level: str | None = None,
) -> str:
    bus_init()
    payload = json.dumps(args or {}, ensure_ascii=False)
    created_at_ts = _now()
    resolved_risk = (risk_level or _risk_for(cmd) or DEFAULT_RISK).upper()
    # retry on transient database locked
    attempts = 0
    while True:
        attempts += 1
        try:
            with _connect() as con:
                if request_id:
                    cur = con.execute(
                        "SELECT cmd_id FROM commands WHERE request_id = ? ORDER BY id DESC LIMIT 1",
                        (request_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return row[0]
                if dedupe_key:
                    cur = con.execute("SELECT cmd_id FROM commands WHERE dedupe_key = ? ORDER BY id DESC LIMIT 1", (dedupe_key,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
                cmd_id = _ensure_cmd_id(con)
                con.execute(
                    """
                    INSERT INTO commands (cmd_id, cmd, args, source, status, dedupe_key, ttl_sec, actor_id, request_id, risk_level, created_at)
                    VALUES (?,?,?,?, 'NEW', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cmd_id,
                        cmd,
                        payload,
                        source,
                        dedupe_key,
                        int(ttl_sec) if ttl_sec else None,
                        actor_id,
                        request_id,
                        resolved_risk,
                        created_at_ts,
                    ),
                )
                _write_audit(
                    con,
                    cmd_id,
                    "enqueue",
                    cmd=cmd,
                    args=args or {},
                    source=source,
                    actor_id=actor_id,
                    request_id=request_id,
                    ttl=ttl_sec,
                    dedupe_key=dedupe_key,
                    risk_level=resolved_risk,
                    created_at=created_at_ts,
                )
                return cmd_id
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempts < 20:
                time.sleep(0.05)
                continue
            raise


@dataclass
class Command:
    cmd_id: str
    cmd: str
    args: dict
    source: str | None
    retry_count: int
    available_at: int
    ttl_sec: int | None
    actor_id: str | None
    request_id: str | None
    risk_level: str
    created_at: int | None


def next_new(now: int | None = None) -> Command | None:
    bus_init()
    ts = now if now is not None else _now()
    expired: list[dict[str, Any]] = []
    with _connect() as con:
        while True:
            cur = con.execute(
                """
                SELECT cmd_id, cmd, args, source, retry_count, available_at, ttl_sec, actor_id, request_id, risk_level, created_at
                FROM commands
                WHERE status='NEW' AND available_at <= ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (ts,),
            )
            row = cur.fetchone()
            if not row:
                break
            ttl_raw = row["ttl_sec"]
            ttl = int(ttl_raw) if ttl_raw is not None else None
            created_at = int(row["created_at"] or 0) if row["created_at"] is not None else 0
            created_at = created_at or int(row["available_at"] or 0)
            if ttl and created_at and ts - created_at > max(0, ttl):
                con.execute("UPDATE commands SET status='EXPIRED' WHERE cmd_id=?", (row["cmd_id"],))
                _write_audit(
                    con,
                    row["cmd_id"],
                    "expired",
                    reason="ttl",
                    created_at=created_at,
                    now=ts,
                    ttl=ttl,
                )
                expired.append(
                    {
                        "cmd_id": row["cmd_id"],
                        "cmd": row["cmd"],
                        "source": row["source"],
                        "actor_id": row["actor_id"],
                        "request_id": row["request_id"],
                        "risk_level": row["risk_level"],
                    }
                )
                continue
            _write_audit(
                con,
                row["cmd_id"],
                "dispatch",
                source=row["source"],
                actor_id=row["actor_id"],
                request_id=row["request_id"],
                risk_level=(row["risk_level"] or DEFAULT_RISK).upper(),
            )
            return Command(
                cmd_id=row["cmd_id"],
                cmd=row["cmd"],
                args=json.loads(row["args"] or "{}"),
                source=row["source"],
                retry_count=int(row["retry_count"] or 0),
                available_at=int(row["available_at"] or 0),
                ttl_sec=ttl,
                actor_id=row["actor_id"],
                request_id=row["request_id"],
                risk_level=(row["risk_level"] or DEFAULT_RISK).upper(),
                created_at=created_at or None,
            )
    for rec in expired:
        emit(
            "warn",
            "command.expired",
            cmd_id=rec["cmd_id"],
            cmd=rec["cmd"],
            source=rec["source"],
            actor_id=rec["actor_id"],
            request_id=rec["request_id"],
            risk=rec["risk_level"],
        )
    return None


def mark_done(cmd_id: str) -> None:
    with _connect() as con:
        con.execute("UPDATE commands SET status='DONE' WHERE cmd_id=?", (cmd_id,))
        _write_audit(con, cmd_id, "done")


def mark_error(cmd_id: str, err: str, retry_backoff_sec: int | None = None) -> None:
    with _connect() as con:
        if retry_backoff_sec is None:
            con.execute("UPDATE commands SET status='ERROR' WHERE cmd_id=?", (cmd_id,))
            _write_audit(con, cmd_id, "error", error=str(err))
        else:
            # increment retry_count and push available_at into the future
            con.execute(
                "UPDATE commands SET retry_count = retry_count + 1, available_at = ? WHERE cmd_id=?",
                (_now() + int(retry_backoff_sec), cmd_id),
            )
            _write_audit(
                con,
                cmd_id,
                "retry",
                error=str(err),
                retry_backoff_sec=int(retry_backoff_sec),
            )
    emit("warn", "command_error", cmd_id=cmd_id, error=err, backoff=retry_backoff_sec)


def emit(level: str, message: str, **fields: Any) -> None:
    bus_init()
    with _connect() as con:
        con.execute(
            "INSERT INTO events (level, message, fields) VALUES (?,?,?)",
            (level, message, json.dumps(fields, ensure_ascii=False) if fields else None),
        )


def _write_audit(con: sqlite3.Connection, cmd_id: str, phase: str, **fields: Any) -> None:
    """Persist an audit log entry; failures are swallowed to not block the bus."""
    try:
        payload = json.dumps(fields, ensure_ascii=False) if fields else None
        con.execute(
            "INSERT INTO command_audit (cmd_id, phase, payload) VALUES (?,?,?)",
            (cmd_id, phase, payload),
        )
    except Exception:
        pass


def stable_request_id(cmd: str, args: dict[str, Any]) -> str:
    payload = {"cmd": cmd, "args": args or {}}
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"{cmd}:{digest}"


def get_approval(approval_id: str) -> dict[str, Any] | None:
    with _connect() as con:
        cur = con.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_approval(row)


def put_approval(record: dict[str, Any]) -> None:
    with _connect() as con:
        con.execute(
            """
            INSERT INTO approvals (approval_id, cmd, target, risk_level, required, approvals, requested_at, expires_at, last_update)
            VALUES (:approval_id, :cmd, :target, :risk_level, :required, :approvals, :requested_at, :expires_at, :last_update)
            ON CONFLICT(approval_id) DO UPDATE SET
              cmd=excluded.cmd,
              target=excluded.target,
              risk_level=excluded.risk_level,
              required=excluded.required,
              approvals=excluded.approvals,
              requested_at=excluded.requested_at,
              expires_at=excluded.expires_at,
              last_update=excluded.last_update
            """,
            {
                **record,
                "approvals": json.dumps(record.get("approvals", []), ensure_ascii=False),
            },
        )


def delete_approval(approval_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM approvals WHERE approval_id=?", (approval_id,))


def list_approvals(include_expired: bool = False, now: int | None = None) -> list[dict[str, Any]]:
    ts = now if now is not None else _now()
    sql = "SELECT * FROM approvals"
    params: tuple[Any, ...] = ()
    if not include_expired:
        sql += " WHERE expires_at > ?"
        params = (ts,)
    with _connect() as con:
        cur = con.execute(sql, params)
        return [_row_to_approval(row) for row in cur.fetchall()]


def prune_expired_approvals(now: int | None = None) -> list[dict[str, Any]]:
    ts = now if now is not None else _now()
    with _connect() as con:
        cur = con.execute("SELECT * FROM approvals WHERE expires_at <= ?", (ts,))
        rows = [_row_to_approval(row) for row in cur.fetchall()]
        if rows:
            con.execute("DELETE FROM approvals WHERE expires_at <= ?", (ts,))
    return rows


def _row_to_approval(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "approval_id": row["approval_id"],
        "cmd": row["cmd"],
        "target": row["target"],
        "risk_level": row["risk_level"],
        "required": int(row["required"]),
        "approvals": json.loads(row["approvals"]) if row["approvals"] else [],
        "requested_at": int(row["requested_at"]),
        "expires_at": int(row["expires_at"]),
        "last_update": int(row["last_update"]),
    }


def set_state(key: str, value: str) -> None:
    """Persist a small app state value.

    Stores as TEXT and updates ISO UTC timestamp.
    """
    from marketlab.core.timefmt import iso_utc  # local import to avoid cycles
    bus_init()
    with _connect() as con:
        con.execute(
            """
            INSERT INTO app_state(key, value, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (str(key), str(value), iso_utc()),
        )


def get_state(key: str, default: str = "") -> str:
    bus_init()
    with _connect() as con:
        cur = con.execute("SELECT value FROM app_state WHERE key=?", (str(key),))
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else str(default)


@dataclass
class Event:
    ts: int
    level: str
    message: str
    fields: dict


def tail_events(limit: int = 200) -> list[Event]:
    bus_init()
    with _connect() as con:
        cur = con.execute(
            "SELECT ts, level, message, fields FROM events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        out: list[Event] = []
        for r in cur.fetchall():
            fields = json.loads(r["fields"]) if r["fields"] else {}
            out.append(Event(ts=int(r["ts"]), level=r["level"], message=r["message"], fields=fields))
        return out
