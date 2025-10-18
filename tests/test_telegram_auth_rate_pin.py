from __future__ import annotations

from tools import tg_poller


def test_requires_pin_for_high_risk():
    assert tg_poller._requires_pin("orders.confirm", "1234") is True
    assert tg_poller._requires_pin("stop.now", "9999") is True
    assert tg_poller._requires_pin("state.pause", "1234") is False


def test_pin_session_helpers(monkeypatch):
    pin_cache: dict[int, float] = {}
    monkeypatch.setattr(tg_poller.time, "time", lambda: 0.0)
    assert tg_poller._pin_session_ok(pin_cache, 100) is False
    tg_poller._set_pin_session(pin_cache, 100)
    assert tg_poller._pin_session_ok(pin_cache, 100) is True
    monkeypatch.setattr(tg_poller.time, "time", lambda: tg_poller.PIN_SESSION_TTL + 1)
    assert tg_poller._pin_session_ok(pin_cache, 100) is False


def test_allow_rate_enforces_window(monkeypatch):
    tracker: dict[int, list[float]] = {}
    monkeypatch.setattr(tg_poller.time, "time", lambda: 0.0)
    assert tg_poller._allow_rate(tracker, 5, 2) is True
    assert tg_poller._allow_rate(tracker, 5, 2) is True
    assert tg_poller._allow_rate(tracker, 5, 2) is False
    monkeypatch.setattr(tg_poller.time, "time", lambda: 61.0)
    assert tg_poller._allow_rate(tracker, 5, 2) is True


def test_action_to_cmd_mapping():
    assert tg_poller._action_to_cmd("stop") == "stop.now"
    assert tg_poller._action_to_cmd("confirm_token") == "orders.confirm"
