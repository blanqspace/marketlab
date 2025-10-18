from __future__ import annotations

import os

from marketlab.daemon.worker import Worker, WorkerConfig
from marketlab.ipc import bus
from marketlab.orders import store as orders
from marketlab.orders.schema import OrderTicket


def setup_db(tmp_path):
    db_path = tmp_path / "ctl.db"
    os.environ[bus.DB_ENV] = str(db_path)
    bus.bus_init()
    return db_path


def test_stop_now_cancels_orders_and_sets_breaker(tmp_path):
    setup_db(tmp_path)
    worker = Worker(cfg=WorkerConfig(two_man_rule=True, confirm_strict=True, ttl_seconds=300))

    # create two pending orders
    orders.put_ticket(OrderTicket.new("AAPL", "BUY", 1.0, "MARKET", None, None, None))
    orders.put_ticket(OrderTicket.new("MSFT", "SELL", 2.0, "LIMIT", 100.0, None, None))

    bus.enqueue(
        "stop.now",
        {},
        source="cli",
        actor_id="cli",
        request_id="stop.now:stop",
        risk_level="CRITICAL",
    )

    assert worker.process_available() == 1

    canceled = orders.list_tickets("CANCELED")
    assert len(canceled) >= 2
    assert bus.get_state("breaker.state") == "killswitch"
    assert bus.get_state("state") == "paused"
    events = bus.tail_events(5)
    assert any(ev.message == "stop.now" for ev in events)


def test_breaker_trips_and_resets(tmp_path):
    setup_db(tmp_path)
    worker = Worker(cfg=WorkerConfig(two_man_rule=False, confirm_strict=True, ttl_seconds=300))

    original_execute = worker._execute

    def boom(self, name: str, args: dict, source: str, approvers: list[str] | None = None) -> bool:
        raise RuntimeError("boom")

    worker._execute = boom.__get__(worker, Worker)  # type: ignore[assignment]

    for _ in range(worker.BREAKER_THRESHOLD):
        bus.enqueue("state.pause", {}, source="cli")
        worker.process_one()

    assert bus.get_state("breaker.state") == "tripped"
    assert worker._breaker_tripped is True
    events = bus.tail_events(5)
    assert any(ev.message == "breaker.tripped" for ev in events)

    # restore execute and resume to clear breaker
    worker._execute = original_execute
    bus.enqueue("state.resume", {}, source="cli")
    worker.process_one()
    assert bus.get_state("breaker.state") == "ok"
    assert worker._breaker_tripped is False
