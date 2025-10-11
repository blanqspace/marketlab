from __future__ import annotations

import os

from src.marketlab.supervisor import _statusline, dispatch, ensure_bus
from src.marketlab.ipc import bus


def test_static_menu_header_and_one_line_message(tmp_path, capsys):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    ensure_bus(db)

    # Header appears as compact single line
    hdr = _statusline(db, None, None)
    assert "DB=" in hdr and "Health=" in hdr and "QueueDepth=" in hdr
    assert "\n" not in hdr

    # Dispatch a short command (pause) -> returns one-line message, prints nothing persistently
    out_before = capsys.readouterr()
    w, d, msg = dispatch("5", db, None, None)
    out_after = capsys.readouterr()
    assert (out_after.out or "").strip() == ""  # no persistent prints
    assert w is None and d is None  # no processes spawned for pause
    assert msg.startswith("OK:") and "\n" not in msg

    # Header again is still compact and not duplicated
    hdr2 = _statusline(db, w, d)
    assert "DB=" in hdr2 and "\n" not in hdr2

