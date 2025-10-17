from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
              ttl_sec INTEGER
            );
            """
        )
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


def _now() -> int:
    return int(time.time())


def _ensure_cmd_id(con: sqlite3.Connection) -> str:
    # Generate a sortable command id using epoch and rowid later
    # Here we just return epoch-ns string for uniqueness
    return f"cmd_{int(time.time()*1e9):d}"


def enqueue(cmd: str, args: dict[str, Any], source: str, ttl_sec: int = 300, dedupe_key: str | None = None) -> str:
    bus_init()
    payload = json.dumps(args or {}, ensure_ascii=False)
    # retry on transient database locked
    attempts = 0
    while True:
        attempts += 1
        try:
            with _connect() as con:
                if dedupe_key:
                    cur = con.execute("SELECT cmd_id FROM commands WHERE dedupe_key = ? ORDER BY id DESC LIMIT 1", (dedupe_key,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
                cmd_id = _ensure_cmd_id(con)
                con.execute(
                    "INSERT INTO commands (cmd_id, cmd, args, source, status, dedupe_key, ttl_sec) VALUES (?,?,?,?, 'NEW', ?, ?)",
                    (cmd_id, cmd, payload, source, dedupe_key, int(ttl_sec) if ttl_sec else None),
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


def next_new(now: int | None = None) -> Command | None:
    bus_init()
    ts = now if now is not None else _now()
    with _connect() as con:
        cur = con.execute(
            "SELECT cmd_id, cmd, args, source, retry_count, available_at, ttl_sec FROM commands WHERE status='NEW' AND available_at <= ? ORDER BY id ASC LIMIT 1",
            (ts,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return Command(
            cmd_id=row["cmd_id"],
            cmd=row["cmd"],
            args=json.loads(row["args"] or "{}"),
            source=row["source"],
            retry_count=int(row["retry_count"] or 0),
            available_at=int(row["available_at"] or 0),
            ttl_sec=int(row["ttl_sec"]) if row["ttl_sec"] is not None else None,
        )


def mark_done(cmd_id: str) -> None:
    with _connect() as con:
        con.execute("UPDATE commands SET status='DONE' WHERE cmd_id=?", (cmd_id,))


def mark_error(cmd_id: str, err: str, retry_backoff_sec: int | None = None) -> None:
    with _connect() as con:
        if retry_backoff_sec is None:
            con.execute("UPDATE commands SET status='ERROR' WHERE cmd_id=?", (cmd_id,))
        else:
            # increment retry_count and push available_at into the future
            con.execute(
                "UPDATE commands SET retry_count = retry_count + 1, available_at = ? WHERE cmd_id=?",
                (_now() + int(retry_backoff_sec), cmd_id),
            )
    emit("warn", "command_error", cmd_id=cmd_id, error=err, backoff=retry_backoff_sec)


def emit(level: str, message: str, **fields: Any) -> None:
    bus_init()
    with _connect() as con:
        con.execute(
            "INSERT INTO events (level, message, fields) VALUES (?,?,?)",
            (level, message, json.dumps(fields, ensure_ascii=False) if fields else None),
        )


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
