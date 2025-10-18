from __future__ import annotations

import os

from marketlab.daemon.worker import Worker, WorkerConfig
from marketlab.core.control_policy import command_target
from marketlab.orders import store as orders
from marketlab.ipc import bus


def setup_db(tmp_path):
    db_path = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db_path)
    bus.bus_init()
    return db_path


def test_two_man_rule_flow(tmp_path, monkeypatch):
    setup_db(tmp_path)
    worker = Worker(cfg=WorkerConfig(two_man_rule=True, confirm_strict=True, ttl_seconds=300))

    monkeypatch.setattr(orders, "resolve_order", lambda sel: {"id": "OID123", "token": "TOK123"})
    monkeypatch.setattr(orders, "resolve_order_by_token", lambda tok: {"id": "OID123", "token": tok})

    args = {"token": "TOK123", "id": "OID123"}
    target = command_target("orders.confirm", args)
    req_id_tg = f"orders.confirm:{target}:tg:alice"
    req_id_cli = f"orders.confirm:{target}:cli:ops"

    cid1 = bus.enqueue(
        "orders.confirm",
        args,
        source="telegram",
        actor_id="tg:alice",
        request_id=req_id_tg,
        risk_level="HIGH",
    )

    assert worker.process_one() is True
    approvals = bus.list_approvals()
    assert approvals and approvals[0]["approval_id"] == f"orders.confirm:{target}"
    events = bus.tail_events(5)
    assert any(e.message == "approval.pending" for e in events)
    assert not any(e.message == "orders.confirm.ok" for e in events)

    cid2 = bus.enqueue(
        "orders.confirm",
        args,
        source="cli",
        actor_id="cli:ops",
        request_id=req_id_cli,
        risk_level="HIGH",
    )

    assert cid1 != cid2

    assert worker.process_one() is True
    approvals_after = bus.list_approvals()
    assert approvals_after == []

    events_after = bus.tail_events(10)
    assert any(e.message == "approval.fulfilled" for e in events_after)
    ok_events = [e for e in events_after if e.message == "orders.confirm.ok"]
    assert ok_events, "missing orders.confirm.ok event"
    assert set(ok_events[0].fields.get("sources") or []) == {"cli", "telegram"}
