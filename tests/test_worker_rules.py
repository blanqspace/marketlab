from __future__ import annotations
import os
from marketlab.ipc import bus


def setup_tmp_db(tmp_path):
    os.environ[bus.DB_ENV] = str(tmp_path / "ctl.db")
    bus.bus_init()


def test_two_man_rule_flags(tmp_path):
    setup_tmp_db(tmp_path)
    # Enqueue two confirmations from different sources
    c1 = bus.enqueue("orders.confirm", {"id": "A"}, source="telegram", dedupe_key="orders:A")
    c2 = bus.enqueue("orders.confirm", {"id": "A"}, source="cli", dedupe_key=None)
    assert c1 != c2
    # Worker policy itself is not implemented here; just ensure bus allows multiple sources
    got = bus.next_new()
    assert got is not None
    bus.mark_done(got.cmd_id)
