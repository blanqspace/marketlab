from __future__ import annotations

import os

from src.marketlab.ipc import bus
from src.marketlab.supervisor import _statusline


def setup_db(tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()
    return db


def test_statusline_contains_health_and_queue(tmp_path):
    db = setup_db(tmp_path)
    # No worker/dash processes in tests
    line = _statusline(db, None, None)
    assert "Health=" in line
    assert "QueueDepth=" in line

