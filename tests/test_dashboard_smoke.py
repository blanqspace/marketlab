from __future__ import annotations

import pytest

from marketlab.tui.dashboard import DashboardApp


@pytest.mark.asyncio
async def test_dashboard_smoke(monkeypatch):
    async def fake_refresh(self):
        self._needs_snapshot = False

    async def fake_stream(self):
        self.exit(result=0)

    monkeypatch.setattr(DashboardApp, "_refresh_snapshot", fake_refresh, raising=False)
    monkeypatch.setattr(DashboardApp, "_stream_events", fake_stream, raising=False)

    app = DashboardApp(db_path=":memory:")
    async with app.run_test() as pilot:
        await pilot.pause()
