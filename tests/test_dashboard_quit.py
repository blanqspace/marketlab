from __future__ import annotations

import pytest

from marketlab.tui.dashboard import DashboardApp


@pytest.mark.asyncio
async def test_dashboard_quit_calls_exit(monkeypatch):
    app = DashboardApp()
    calls = {"exit": 0, "shutdown": 0}

    def fake_exit(*_args, **_kwargs):
        calls["exit"] += 1

    monkeypatch.setattr(app, "exit", fake_exit, raising=True)

    if hasattr(app, "shutdown"):

        async def fake_shutdown(*_args, **_kwargs):  # pragma: no cover
            calls["shutdown"] += 1

        monkeypatch.setattr(app, "shutdown", fake_shutdown, raising=True)

    await app.action_quit()

    assert calls["exit"] == 1
    assert calls["shutdown"] == 0
