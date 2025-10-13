from __future__ import annotations

import os
from marketlab.ipc import bus
from marketlab.daemon.worker import Worker


def with_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_state_and_mode_events(tmp_path):
    with_tmp_db(tmp_path)
    w = Worker()

    # pause
    bus.enqueue("state.pause", {}, source="cli")
    assert w.process_available() == 1
    ev = bus.tail_events(1)[0]
    assert ev.message == "state.changed"
    assert ev.level == "ok"
    assert ev.fields.get("state") == "PAUSED"

    # resume
    bus.enqueue("state.resume", {}, source="cli")
    w.process_available()
    ev = bus.tail_events(1)[0]
    assert ev.message == "state.changed"
    assert ev.fields.get("state") == "RUN"

    # stop
    bus.enqueue("state.stop", {}, source="cli")
    w.process_available()
    ev = bus.tail_events(1)[0]
    assert ev.message == "state.changed"
    assert ev.fields.get("state") == "STOP"

    # mode switch
    bus.enqueue("mode.switch", {"target": "paper"}, source="cli")
    w.process_available()
    ev = bus.tail_events(1)[0]
    assert ev.message == "mode.enter"
    assert ev.level == "info"
    assert ev.fields.get("mode") == "paper"

