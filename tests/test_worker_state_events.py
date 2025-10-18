from __future__ import annotations

import os
from marketlab.ipc import bus
from marketlab.daemon.worker import Worker


def setup_db(tmp_path):
    db = str(tmp_path / "ctl.db")
    os.environ[bus.DB_ENV] = db
    bus.bus_init()
    return db


def test_pause_resume_mode_sets_and_emits(tmp_path):
    setup_db(tmp_path)
    w = Worker()

    # pause -> app_state updated, event emitted (legacy uppercase)
    bus.enqueue("state.pause", {}, source="cli")
    assert w.process_available() == 1
    assert bus.get_state("state", "") == "paused"
    ev = bus.tail_events(1)[0]
    assert ev.message == "state.changed"

    # resume
    bus.enqueue("state.resume", {}, source="cli")
    w.process_available()
    assert bus.get_state("state", "") == "running"
    ev = bus.tail_events(1)[0]
    assert ev.message == "state.changed"

    # mode switch
    bus.enqueue("mode.switch", {"target": "paper"}, source="cli")
    w.process_available()
    assert bus.get_state("mode", "-") == "paper"
    ev = bus.tail_events(1)[0]
    assert ev.message == "mode.enter"
