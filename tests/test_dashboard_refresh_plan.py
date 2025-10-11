from __future__ import annotations

from tools.tui_dashboard import _plan_tick


def test_scheduler_decides_per_spec():
    now = 100.0
    ev_every = 2
    kpi_every = 15
    ne, no, nk = 0.0, 0.0, 0.0
    # at t=100, all due
    upd, (ne, no, nk) = _plan_tick(now, ne, no, nk, events_changed=False, ev_every=ev_every, kpi_every=kpi_every)
    assert upd["events"] and upd["orders"] and upd["kpis"]
    assert int(ne - now) == ev_every
    assert int(no - now) == ev_every
    assert int(nk - now) == kpi_every

    # No new events, advance slightly <2s -> nothing due
    upd, (ne, no, nk) = _plan_tick(now + 1.0, ne, no, nk, events_changed=False, ev_every=ev_every, kpi_every=kpi_every)
    assert not any(upd.values())

    # New event arrives -> events due immediately
    upd, (ne, no, nk) = _plan_tick(now + 1.1, ne, no, nk, events_changed=True, ev_every=ev_every, kpi_every=kpi_every)
    assert upd["events"] and not upd["orders"] and not upd["kpis"]

    # At >=2s -> orders/events refresh
    upd, (ne, no, nk) = _plan_tick(now + 2.1, ne, no, nk, events_changed=False, ev_every=ev_every, kpi_every=kpi_every)
    assert upd["events"] or upd["orders"]

