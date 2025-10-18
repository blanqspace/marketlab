from __future__ import annotations

import signal
import threading
import time

import pytest

from tools.proc_guard import ProcGuard


class DummyProcess:
    def __init__(self, poll_results: list[int | None]) -> None:
        self.poll_results = list(poll_results)
        self.pid = 4242

    def poll(self) -> int | None:
        if self.poll_results:
            value = self.poll_results[0]
            if value is not None or len(self.poll_results) == 1:
                self.poll_results.pop(0)
            return value
        return None

    def wait(self, timeout=None):  # pragma: no cover - unused
        return 0


def test_guard_exits_cleanly(monkeypatch):
    proc = DummyProcess([0])
    monkeypatch.setattr("tools.proc_guard.os.killpg", lambda pid, sig: None)
    guard = ProcGuard(
        "demo", ["sleep", "0"], popen_factory=lambda *a, **k: proc, sleep_fn=lambda _t: None
    )
    assert guard.run() == 0


def test_guard_escalates_signals(monkeypatch):
    proc = DummyProcess([None, None, 0])
    sent: list[int] = []

    def fake_killpg(pid, sig):
        sent.append(sig)

    monkeypatch.setattr("tools.proc_guard.os.killpg", fake_killpg)
    guard = ProcGuard(
        "hung",
        ["sleep", "999"],
        popen_factory=lambda *a, **k: proc,
        sleep_fn=lambda _t: None,
        sigint_timeout=0,
        sigterm_timeout=0,
    )

    results: list[int] = []

    def runner():
        results.append(guard.run())

    thread = threading.Thread(target=runner)
    thread.start()
    while guard._proc is None:  # pragma: no cover - waiting for spawn
        time.sleep(0.01)
    guard._handle_signal(signal.SIGINT, None)
    thread.join(timeout=1)
    assert results == [0]
    assert sent == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]


def test_guard_health_check_stops(monkeypatch):
    proc = DummyProcess([None, 0])
    sent: list[int] = []

    def fake_killpg(pid, sig):
        sent.append(sig)

    monkeypatch.setattr("tools.proc_guard.os.killpg", fake_killpg)
    calls = {"count": 0}

    def health() -> bool:
        calls["count"] += 1
        return calls["count"] < 2

    guard = ProcGuard(
        "health",
        ["sleep", "10"],
        popen_factory=lambda *a, **k: proc,
        sleep_fn=lambda _t: None,
        check_interval=0,
        sigint_timeout=0,
        sigterm_timeout=0,
        health_check=health,
    )
    assert guard.run() == 0
    assert sent[0] == signal.SIGINT
    assert calls["count"] >= 2
