from __future__ import annotations

import os

from marketlab.supervisor import dispatch, ensure_bus
from marketlab.ipc import bus


def test_tail_events_once_shows_10_and_returns(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    ensure_bus(db)

    # emit >10 events
    for i in range(15):
        bus.emit("info", f"event_{i}")

    # prevent blocking on input prompt within dispatch('12')
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    # run tail once
    w, d, p, msg = dispatch("12", db, None, None)
    captured = capsys.readouterr()

    # It should print at most 10 lines (aggregated) and then return
    lines = [ln for ln in captured.out.strip().splitlines() if ln.strip()]
    assert 1 <= len(lines) <= 10
    # no status message enforced for tail
    assert isinstance(msg, str)
