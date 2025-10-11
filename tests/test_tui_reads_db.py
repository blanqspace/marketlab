from __future__ import annotations

import os, sys, subprocess
from src.marketlab.ipc import bus
from src.marketlab.settings import settings as app_settings
from tools.tui_dashboard import _header
from rich.console import Console
import os as _os


def with_tmp_db(tmp_path):
    dbp = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(dbp)
    bus.bus_init()
    # ensure TUI and bus use the same DB via settings
    app_settings.ipc_db = str(dbp)
    return dbp


def test_tui_header_shows_db_and_events_after_drain(tmp_path):
    dbp = with_tmp_db(tmp_path)
    # enqueue a simple command
    bus.enqueue("state.pause", {}, source="cli")
    # drain via CLI worker apply
    out = subprocess.run(
        [sys.executable, "-m", "marketlab", "ctl", "drain", "--apply", "--limit", "5"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 0
    # events should contain state.changed emitted by worker
    ev = bus.tail_events(1)[0]
    assert ev.message in ("state.changed",)
    # header should include DB basename
    pnl = _header()
    console = Console(width=120, record=True)
    console.print(pnl)
    rendered = console.export_text()
    assert f"DB={_os.path.basename(str(dbp))}" in rendered
