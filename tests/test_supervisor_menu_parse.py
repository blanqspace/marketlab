import json
import os
import sqlite3

from marketlab.supervisor import ensure_bus, _resolve_token_or_index
from marketlab.ipc import bus


def test_parse_confirm_token_enqueues(tmp_path, monkeypatch):
    db_path = str(tmp_path / "ctl.db")
    monkeypatch.setenv("IPC_DB", db_path)
    ensure_bus(db_path)

    # Simulate user input parsing for token
    mode, val = _resolve_token_or_index("ABC7QK")
    assert mode == "token"
    assert val == "ABC7QK"

    cmd_id = bus.enqueue("orders.confirm", {"token": val}, source="test")
    # verify latest command has correct args
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT cmd, args FROM commands WHERE cmd_id=?",
            (cmd_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "orders.confirm"
        args = json.loads(row[1])
        assert args.get("token") == "ABC7QK"
    finally:
        con.close()
