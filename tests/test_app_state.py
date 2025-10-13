from __future__ import annotations

import os

from marketlab.ipc import bus


def test_set_get_state_roundtrip(tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()

    bus.set_state("state", "running")
    bus.set_state("mode", "paper")

    assert bus.get_state("state", "INIT") == "running"
    assert bus.get_state("mode", "-") == "paper"

