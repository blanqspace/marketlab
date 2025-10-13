"""Orders token migration tool.

Adds a `token` column to persistent DB (if exists), creates a unique index,
and backfills tokens for orders missing them. Emits an event upon completion.
Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Tuple

from marketlab.ipc import bus
from marketlab.orders.store import new_token


def _connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def migrate_orders_token(db_path: str) -> Tuple[int, bool]:
    """Run migration. Returns (migrated_count, schema_changed)."""
    if not os.path.exists(db_path):
        return (0, False)
    changed = False
    migrated = 0
    with _connect(db_path) as con:
        # Check if table orders exists
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        if not cur.fetchone():
            return (0, False)
        # Add token column if missing
        cols = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
        if "token" not in cols:
            con.execute("ALTER TABLE orders ADD COLUMN token TEXT")
            changed = True
        # Create unique index on token
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_token ON orders(token)")
        # Backfill missing tokens
        rows = con.execute("SELECT id, token FROM orders").fetchall()
        existing = {str(r["token"]).upper() for r in rows if r["token"]}
        for r in rows:
            if not r["token"]:
                tok = new_token(existing, 6)
                existing.add(tok.upper())
                con.execute("UPDATE orders SET token=? WHERE id=?", (tok, r["id"]))
                migrated += 1
    # Emit migration event
    bus.emit("ok", "orders.token.migration.done", migrated=migrated)
    return (migrated, changed)


if __name__ == "__main__":  # pragma: no cover
    db = os.environ.get("IPC_DB", "runtime/ctl.db")
    migrated, schema_changed = migrate_orders_token(db)
    print({"migrated": migrated, "schema_changed": schema_changed})

